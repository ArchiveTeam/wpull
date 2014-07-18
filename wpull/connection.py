# encoding=utf8
'''Network connections.'''
import contextlib
import errno
import logging
import os
import socket
import ssl

import tornado.netutil
from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.dns import Resolver
from wpull.errors import NetworkError, ConnectionRefused, SSLVerficationError, \
    NetworkTimedOut


_logger = logging.getLogger(__name__)


class HostPool(object):
    '''Connection pool for a host.

    Attributes:
        ready (Queue): Connections not in use.
        busy (set): Connections in use.
    '''
    def __init__(self):
        self.ready = trollius.Queue()
        self.busy = set()

    def empty(self):
        '''Return whether the pool is empty.'''
        return self.ready.empty() and not self.busy

    def clean(self):
        '''Clean closed connections.'''
        connected = []
        while True:
            try:
                connection = self.ready.get_nowait()
            except trollius.QueueEmpty:
                break
            if not connection.closed():
                connected.append(connection)

        while connected:
            connection = connected.pop()
            self.ready.put_nowait(connection)

    def close(self):
        '''Close all connections.'''
        while True:
            try:
                connection = self.ready.get_nowait()
            except trollius.QueueEmpty:
                break
            else:
                connection.close()

        for connection in self.busy:
            connection.close()


class ConnectionPool(object):
    '''Connection pool.

    Args:
        max_host_count (int): Number of connections per host.
        resolver (:class:`.dns.Resolver`): DNS resolver.
        connection_factory: A function that accepts ``address`` and
            ``hostname`` arguments and returns a :class:`Connection` instance.
        ssl_connection_factory: A function that returns a
            :class:`SSLConnection` instance. See `connection_factory`.
    '''
    def __init__(self, max_host_count=6, resolver=None,
                 connection_factory=None, ssl_connection_factory=None):
        self._max_host_count = max_host_count
        self._resolver = resolver or Resolver()
        self._connection_factory = connection_factory or Connection
        self._ssl_connection_factory = ssl_connection_factory or SSLConnection
        self._pool = {}

        self._clean_cb()

    @trollius.coroutine
    def check_out(self, host, port, ssl=False):
        '''Return an available connection.'''
        address = yield From(self._resolver.resolve(host, port))
        key = (host, port, ssl)

        if key not in self._pool:
            host_pool = self._pool[key] = HostPool()
        else:
            host_pool = self._pool[key]

        if host_pool.ready.empty() \
                and len(host_pool.busy) < self._max_host_count:
            if ssl:
                connection = self._ssl_connection_factory(address, host)
            else:
                connection = self._connection_factory(address, host)
        else:
            connection = yield From(host_pool.ready.get())

        host_pool.busy.add(connection)

        raise Return(connection)

    def check_in(self, connection):
        '''Put a connection back in the pool.'''
        key = (connection.hostname, connection.port, connection.ssl)
        host_pool = self._pool[key]

        host_pool.busy.remove(connection)

        if not connection.closed():
            host_pool.ready.put_nowait(connection)

    @trollius.coroutine
    def session(self, host, port, ssl=False):
        '''Return a context manager that returns a connection.'''
        connection = yield From(self.check_out(host, port, ssl))

        @contextlib.contextmanager
        def context_wrapper():
            try:
                yield connection
            finally:
                self.check_in(connection)

        return context_wrapper()

    def clean(self):
        '''Clean all closed connections.'''
        for pool in tuple(self._pool):
            pool.close()
            if pool.empty():
                del self._pool[pool]

    def close(self):
        '''Close all the connections.'''
        for pool in tuple(self._pool):
            pool.close()
            del self._pool[pool]

    def _clean_cb(self):
        '''Clean timer callback.'''
        _logger.debug('Periodic connection clean.')
        self.clean()
        trollius.get_event_loop().call_later(300, self._clean_cb)


class Connection(object):
    '''Network stream.

    Args:
        address (tuple): 2-item tuple containing the IP address and port.
        hostname (str): Hostname of the address (for SSL).
        timeout (float): Time in seconds before a read/write operation
            times out.
        connect_timeout (float): Time in seconds before a connect operation
            times out.
        bind_host (str): Host name for binding the socket interface.

    Attributes:
        reader: Stream Reader instance.
        writer: Stream Writer instance.
        bandwidth_limiter: BandwidthLimiter instance.
        address: 2-item tuple containing the IP address.
        host (str): Host name.
        port (int): Port number.
        ssl (bool): Whether connection is SSL.
    '''
    def __init__(self, address, hostname=None, timeout=None,
                 connect_timeout=None, bind_host=None):
        self._address = address
        self._hostname = hostname or address[0]
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._bind_host = bind_host
        self.reader = None
        self.writer = None
        self.bandwidth_limiter = None

        # TODO: implement bandwidth limiting

    @property
    def address(self):
        return self._address

    @property
    def hostname(self):
        return self._hostname

    @property
    def host(self):
        return self._address[0]

    @property
    def port(self):
        return self._address[1]

    @property
    def ssl(self):
        return False

    def closed(self):
        '''Return whether the connection is closed.'''
        return not self.reader or self.reader.at_eof()

    @trollius.coroutine
    def connect(self):
        '''Establish a connection.'''
        _logger.debug(__('Connecting to {0}.', self._address))

        try:
            host, port = self._address
            connection_future = trollius.open_connection(
                host, port, **self._connection_kwargs()
            )
            self.reader, self.writer = yield From(
                trollius.wait_for(connection_future, self._connect_timeout)
            )
        except trollius.TimeoutError as error:
            raise NetworkTimedOut(
                'Connection timed out: {error}'.format(error=error)) from error
        except (tornado.netutil.SSLCertificateError,
                SSLVerficationError) as error:
            raise SSLVerficationError(
                'Certificate error: {error}'.format(error=error)) from error
        except (socket.error, ssl.SSLError) as error:
            if error.errno == errno.ECONNREFUSED:
                raise ConnectionRefused(error.errno, os.strerror(error.errno))
            else:
                raise NetworkError(error.errno, os.strerror(error.errno))
        else:
            _logger.debug('Connected.')

    def _connection_kwargs(self):
        '''Return additional connection arguments.'''
        kwargs = {}

        if self._bind_host:
            kwargs['local_addr'] = (self._bind_host, 0)

        return kwargs

    def close(self):
        '''Close the connection.'''
        if self.writer:
            self.writer.close()

            self.writer = None
            self.reader = None

    @trollius.coroutine
    def write(self, data):
        '''Write data.'''
        self.writer.write(data)

        fut = self.writer.drain()

        if fut:
            try:
                yield From(trollius.wait_for(fut, self._timeout))
            except trollius.TimeoutError as error:
                raise NetworkTimedOut('Write timed out.') from error

    @trollius.coroutine
    def read(self, amount=-1):
        '''Read data.'''
        try:
            data = yield From(trollius.wait_for(self.reader.read(amount),
                                                self._timeout))
            raise Return(data)
        except trollius.TimeoutError as error:
            raise NetworkTimedOut('Read timed out.') from error

    @trollius.coroutine
    def readline(self):
        '''Read a line of data.'''
        try:
            data = yield From(trollius.wait_for(self.reader.readline(),
                                                self._timeout))
            raise Return(data)
        except trollius.TimeoutError as error:
            raise NetworkTimedOut('Read timed out.') from error


class SSLConnection(Connection):
    '''SSL network stream.

    Args:
        ssl_context: SSLContext
    '''
    def __init__(self, *args, ssl_context=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._ssl_context = ssl_context

    @property
    def ssl(self):
        return True

    def _connection_kwargs(self):
        kwargs = super()._connection_kwargs()

        if self._ssl_context:
            kwargs['ssl'] = self._ssl_context
            kwargs['server_hostname'] = self._hostname

            return kwargs
