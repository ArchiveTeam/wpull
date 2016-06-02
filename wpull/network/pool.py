import asyncio
import contextlib
import functools
import logging

from typing import Callable, Optional, Mapping, Any, Union, Tuple

from wpull.cache import FIFOCache
from wpull.errors import NetworkError
from wpull.network.connection import Connection, SSLConnection
from wpull.network.dns import Resolver, ResolveResult

_logger = logging.getLogger(__name__)


class HostPool(object):
    '''Connection pool for a host.

    Attributes:
        ready (Queue): Connections not in use.
        busy (set): Connections in use.
    '''
    def __init__(self, connection_factory: Callable[[], Connection],
                 max_connections: int=6):
        assert max_connections > 0, \
            'num must be positive. got {}'.format(max_connections)

        self._connection_factory = connection_factory
        self.max_connections = max_connections
        self.ready = set()
        self.busy = set()
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(lock=self._lock)
        self._closed = False

    def empty(self) -> bool:
        '''Return whether the pool is empty.'''
        return not self.ready and not self.busy

    @asyncio.coroutine
    def clean(self, force: bool=False):
        '''Clean closed connections.

        Args:
            force: Clean connected and idle connections too.

        Coroutine.
        '''
        with (yield from self._lock):
            for connection in tuple(self.ready):
                if force or connection.closed():
                    connection.close()
                    self.ready.remove(connection)

    def close(self):
        '''Forcibly close all connections.

        This instance will not be usable after calling this method.
        '''
        for connection in self.ready:
            connection.close()

        for connection in self.busy:
            connection.close()

        self._closed = True

    def count(self) -> int:
        '''Return total number of connections.'''
        return len(self.ready) + len(self.busy)

    @asyncio.coroutine
    def acquire(self) -> Connection:
        '''Register and return a connection.

        Coroutine.
        '''
        assert not self._closed

        yield from self._condition.acquire()

        while True:
            if self.ready:
                connection = self.ready.pop()
                break
            elif len(self.busy) < self.max_connections:
                connection = self._connection_factory()
                break
            else:
                yield from self._condition.wait()

        self.busy.add(connection)
        self._condition.release()

        return connection

    @asyncio.coroutine
    def release(self, connection: Connection, reuse: bool=True):
        '''Unregister a connection.

        Args:
            connection: Connection instance returned from :meth:`acquire`.
            reuse: If True, the connection is made available for reuse.

        Coroutine.
        '''
        yield from self._condition.acquire()
        self.busy.remove(connection)

        if reuse:
            self.ready.add(connection)

        self._condition.notify()
        self._condition.release()


class ConnectionPool(object):
    '''Connection pool.

    Args:
        max_host_count: Number of connections per host.
        resolver: DNS resolver.
        connection_factory: A function that accepts ``address`` and
            ``hostname`` arguments and returns a :class:`Connection` instance.
        ssl_connection_factory: A function that returns a
            :class:`SSLConnection` instance. See `connection_factory`.
        max_count: Limit on number of connections
    '''
    def __init__(self, max_host_count: int=6,
                 resolver: Optional[Resolver]=None,
                 connection_factory:
                 Optional[Callable[[tuple, str], Connection]]=None,
                 ssl_connection_factory:
                 Optional[Callable[[tuple, str], SSLConnection]]=None,
                 max_count: int=100):
        self._max_host_count = max_host_count
        self._resolver = resolver or Resolver()
        self._connection_factory = connection_factory or Connection
        self._ssl_connection_factory = ssl_connection_factory or SSLConnection
        self._max_count = max_count
        self._host_pools = {}
        self._host_pool_waiters = {}
        self._host_pools_lock = asyncio.Lock()
        self._release_tasks = set()
        self._closed = False
        self._happy_eyeballs_table = HappyEyeballsTable()

    @property
    def host_pools(self) -> Mapping[tuple, HostPool]:
        return self._host_pools

    @asyncio.coroutine
    def acquire(self, host: str, port: int, use_ssl: bool=False,
                host_key: Optional[Any]=None) \
            -> Union[Connection, SSLConnection]:
        '''Return an available connection.

        Args:
            host: A hostname or IP address.
            port: Port number.
            use_ssl: Whether to return a SSL connection.
            host_key: If provided, it overrides the key used for per-host
                connection pooling. This is useful for proxies for example.

        Coroutine.
        '''
        assert isinstance(port, int), 'Expect int. Got {}'.format(type(port))
        assert not self._closed

        yield from self._process_no_wait_releases()

        if use_ssl:
            connection_factory = functools.partial(
                self._ssl_connection_factory, hostname=host)
        else:
            connection_factory = functools.partial(
                self._connection_factory, hostname=host)

        connection_factory = functools.partial(
            HappyEyeballsConnection, (host, port), connection_factory,
            self._resolver, self._happy_eyeballs_table,
            is_ssl=use_ssl
        )

        key = host_key or (host, port, use_ssl)

        with (yield from self._host_pools_lock):
            if key not in self._host_pools:
                host_pool = self._host_pools[key] = HostPool(
                    connection_factory,
                    max_connections=self._max_host_count
                )
                self._host_pool_waiters[key] = 1
            else:
                host_pool = self._host_pools[key]
                self._host_pool_waiters[key] += 1

        _logger.debug('Check out %s', key)

        connection = yield from host_pool.acquire()
        connection.key = key

        # TODO: Verify this assert is always true
        # assert host_pool.count() <= host_pool.max_connections
        # assert key in self._host_pools
        # assert self._host_pools[key] == host_pool

        with (yield from self._host_pools_lock):
            self._host_pool_waiters[key] -= 1

        return connection

    @asyncio.coroutine
    def release(self, connection: Connection):
        '''Put a connection back in the pool.

        Coroutine.
        '''
        assert not self._closed

        key = connection.key
        host_pool = self._host_pools[key]

        _logger.debug('Check in %s', key)

        yield from host_pool.release(connection)

        force = self.count() > self._max_count
        yield from self.clean(force=force)

    def no_wait_release(self, connection: Connection):
        '''Synchronous version of :meth:`release`.'''
        _logger.debug('No wait check in.')
        release_task = asyncio.get_event_loop().create_task(
            self.release(connection)
        )
        self._release_tasks.add(release_task)

    @asyncio.coroutine
    def _process_no_wait_releases(self):
        '''Process check in tasks.'''
        while True:
            try:
                release_task = self._release_tasks.pop()
            except KeyError:
                return
            else:
                yield from release_task

    @asyncio.coroutine
    def session(self, host: str, port: int, use_ssl: bool=False):
        '''Return a context manager that returns a connection.

        Usage::

            session = yield from connection_pool.session('example.com', 80)
            with session as connection:
                connection.write(b'blah')
                connection.close()

        Coroutine.
        '''
        connection = yield from self.acquire(host, port, use_ssl)

        @contextlib.contextmanager
        def context_wrapper():
            try:
                yield connection
            finally:
                self.no_wait_release(connection)

        return context_wrapper()

    @asyncio.coroutine
    def clean(self, force: bool=False):
        '''Clean all closed connections.

        Args:
            force: Clean connected and idle connections too.

        Coroutine.
        '''
        assert not self._closed

        with (yield from self._host_pools_lock):
            for key, pool in tuple(self._host_pools.items()):
                yield from pool.clean(force=force)

                if not self._host_pool_waiters[key] and pool.empty():
                    del self._host_pools[key]
                    del self._host_pool_waiters[key]

    def close(self):
        '''Close all the connections and clean up.

        This instance will not be usable after calling this method.
        '''
        for key, pool in tuple(self._host_pools.items()):
            pool.close()

            del self._host_pools[key]
            del self._host_pool_waiters[key]

        self._closed = True

    def count(self) -> int:
        '''Return number of connections.'''
        counter = 0

        for pool in self._host_pools.values():
            counter += pool.count()

        return counter


class HappyEyeballsTable(object):
    def __init__(self, max_items=100, time_to_live=600):
        '''Happy eyeballs connection cache table.'''
        self._cache = FIFOCache(max_items=max_items, time_to_live=time_to_live)

    def set_preferred(self, preferred_addr, addr_1, addr_2):
        '''Set the preferred address.'''
        if addr_1 > addr_2:
            addr_1, addr_2 = addr_2, addr_1

        self._cache[(addr_1, addr_2)] = preferred_addr

    def get_preferred(self, addr_1, addr_2):
        '''Return the preferred address.'''
        if addr_1 > addr_2:
            addr_1, addr_2 = addr_2, addr_1

        return self._cache.get((addr_1, addr_2))


class HappyEyeballsConnection(object):
    '''Wrapper for happy eyeballs connection.'''
    def __init__(self, address, connection_factory, resolver,
                 happy_eyeballs_table, is_ssl=False):
        self._address = address
        self._connection_factory = connection_factory
        self._resolver = resolver
        self._happy_eyeballs_table = happy_eyeballs_table
        self._primary_connection = None
        self._secondary_connection = None
        self._active_connection = None
        self.key = None
        self.proxied = False
        self.tunneled = False
        self.ssl = is_ssl

    def __getattr__(self, item):
        return getattr(self._active_connection, item)

    def closed(self):
        if self._active_connection:
            return self._active_connection.closed()
        else:
            return True

    def close(self):
        if self._active_connection:
            self._active_connection.close()

    def reset(self):
        if self._active_connection:
            self._active_connection.reset()

    @asyncio.coroutine
    def connect(self):
        if self._active_connection:
            yield from self._active_connection.connect()
            return

        result = yield from self._resolver.resolve(self._address[0])

        primary_host, secondary_host = self._get_preferred_host(result)

        if not secondary_host:
            self._primary_connection = self._active_connection = \
                self._connection_factory((primary_host, self._address[1]))
            yield from self._primary_connection.connect()
        else:
            yield from self._connect_dual_stack(
                (primary_host, self._address[1]),
                (secondary_host, self._address[1])
            )

    @asyncio.coroutine
    def _connect_dual_stack(self, primary_address, secondary_address):
        '''Connect using happy eyeballs.'''
        self._primary_connection = self._connection_factory(primary_address)
        self._secondary_connection = self._connection_factory(secondary_address)

        @asyncio.coroutine
        def connect_primary():
            yield from self._primary_connection.connect()
            return self._primary_connection

        @asyncio.coroutine
        def connect_secondary():
            yield from self._secondary_connection.connect()
            return self._secondary_connection

        primary_fut = connect_primary()
        secondary_fut = connect_secondary()

        failed = False

        for fut in asyncio.as_completed((primary_fut, secondary_fut)):
            if not self._active_connection:
                try:
                    self._active_connection = yield from fut
                except NetworkError:
                    if not failed:
                        _logger.debug('Original dual stack exception', exc_info=True)
                        failed = True
                    else:
                        raise
                else:
                    _logger.debug('Got first of dual stack.')

            else:
                @asyncio.coroutine
                def cleanup():
                    try:
                        conn = yield from fut
                    except NetworkError:
                        pass
                    else:
                        conn.close()
                    _logger.debug('Closed abandoned connection.')

                asyncio.get_event_loop().create_task(cleanup())

        preferred_host = self._active_connection.host

        self._happy_eyeballs_table.set_preferred(
            preferred_host, primary_address[0], secondary_address[0])

    def _get_preferred_host(self, result: ResolveResult) -> Tuple[str, str]:
        '''Get preferred host from DNS results.'''
        host_1 = result.first_ipv4.ip_address if result.first_ipv4 else None
        host_2 = result.first_ipv6.ip_address if result.first_ipv6 else None

        if not host_2:
            return host_1, None
        elif not host_1:
            return host_2, None

        preferred_host = self._happy_eyeballs_table.get_preferred(
            host_1, host_2)

        if preferred_host:
            return preferred_host, None
        else:
            return host_1, host_2
