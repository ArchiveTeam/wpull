# encoding=utf8
'''Network connections.'''
import contextlib
import errno
import functools
import logging
import os
import socket
import ssl

from tornado.netutil import SSLCertificateError
from trollius import From, Return
import tornado.netutil
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.dns import Resolver
from wpull.errors import NetworkError, ConnectionRefused, SSLVerificationError, \
    NetworkTimedOut


_logger = logging.getLogger(__name__)


class CloseTimer(object):
    '''Periodic timer to close connections if stalled.'''
    def __init__(self, timeout, connection):
        self._timeout = timeout
        self._touch_time = None
        self._call_later_handle = None
        self._connection = connection
        self._event_loop = trollius.get_event_loop()
        self._timed_out = False
        self._running = True

        assert self._timeout > 0
        self._schedule()

    def _schedule(self):
        '''Schedule check function.'''
        if self._running:
            _logger.debug('Schedule check function.')
            self._call_later_handle = self._event_loop.call_later(
                self._timeout, self._check)

    def _check(self):
        '''Check and close connection if needed.'''
        _logger.debug('Check if timeout.')
        self._call_later_handle = None

        if self._touch_time is not None:
            difference = self._event_loop.time() - self._touch_time
            _logger.debug('Time difference %s', difference)

            if difference > self._timeout:
                self._connection.close()
                self._timed_out = True

        if not self._connection.closed():
            self._schedule()

    def close(self):
        '''Stop running timers.'''
        if self._call_later_handle:
            self._call_later_handle.cancel()

        self._running = False

    @contextlib.contextmanager
    def with_timeout(self):
        '''Context manager that applies timeout checks.'''
        self._touch_time = self._event_loop.time()
        try:
            yield
        finally:
            self._touch_time = None

    def is_timeout(self):
        return self._timed_out


class DummyCloseTimer(object):
    '''Dummy close timer.'''
    @contextlib.contextmanager
    def with_timeout(self):
        yield

    def is_timeout(self):
        return False

    def close(self):
        pass


class HostPool(object):
    '''Connection pool for a host.

    Attributes:
        ready (Queue): Connections not in use.
        busy (set): Connections in use.
    '''
    def __init__(self, max_connections=6):
        assert max_connections > 0, \
            'num must be positive. got {}'.format(max_connections)

        self.max_connections = max_connections
        self.ready = set()
        self.busy = set()
        self._ready_event = trollius.Event()

    def empty(self):
        '''Return whether the pool is empty.'''
        return not self.ready and not self.busy

    def clean(self, force=False):
        '''Clean closed connections.'''
        for connection in tuple(self.ready):
            if force or connection.closed():
                connection.close()
                self.ready.remove(connection)

    def close(self):
        '''Close all connections.'''
        for connection in self.ready:
            connection.close()

        for connection in self.busy:
            connection.close()

    def count(self):
        '''Return total number of connections.'''
        return len(self.ready) + len(self.busy)

    @trollius.coroutine
    def check_out(self, connection_factory):
        while True:
            if self.ready:
                connection = self.ready.pop()
                break
            elif len(self.busy) < self.max_connections:
                connection = connection_factory()
                break
            else:
                # We should be using a Condition but check_in
                # must be synchronous
                yield From(self._ready_event.wait())
                self._ready_event.clear()

        self.busy.add(connection)
        raise Return(connection)

    def check_in(self, connection):
        self.busy.remove(connection)
        self.ready.add(connection)
        self._ready_event.set()


class ConnectionPool(object):
    '''Connection pool.

    Args:
        max_host_count (int): Number of connections per host.
        resolver (:class:`.dns.Resolver`): DNS resolver.
        connection_factory: A function that accepts ``address`` and
            ``hostname`` arguments and returns a :class:`Connection` instance.
        ssl_connection_factory: A function that returns a
            :class:`SSLConnection` instance. See `connection_factory`.
        max_count (int): Limit on number of connections
    '''
    def __init__(self, max_host_count=6, resolver=None,
                 connection_factory=None, ssl_connection_factory=None,
                 max_count=100):
        self._max_host_count = max_host_count
        self._resolver = resolver or Resolver()
        self._connection_factory = connection_factory or Connection
        self._ssl_connection_factory = ssl_connection_factory or SSLConnection
        self._max_count = max_count
        self._pool = {}

        self._clean_cb()

    @property
    def pool(self):
        return self._pool

    @trollius.coroutine
    def check_out(self, host, port, ssl=False):
        '''Return an available connection.

        Coroutine.
        '''
        assert isinstance(port, int), 'Expect int. Got {}'.format(type(port))

        family, address = yield From(self._resolver.resolve(host, port))
        key = (host, port, ssl)

        if key not in self._pool:
            host_pool = self._pool[key] = HostPool(
                max_connections=self._max_host_count
            )
        else:
            host_pool = self._pool[key]

        if ssl:
            connection_factory = functools.partial(
                self._ssl_connection_factory, address, host)
        else:
            connection_factory = functools.partial(
                self._connection_factory, address, host)

        connection = yield From(host_pool.check_out(connection_factory))

        # XXX: Verify this assert is always true
        # assert host_pool.count() <= host_pool.max_connections
        # assert key in self._pool
        # assert self._pool[key] == host_pool

        if key not in self._pool:
            # XXX: Pool may have been deleted during a clean which shouldn't
            # happen
            self._pool[key] = host_pool

        raise Return(connection)

    def check_in(self, connection):
        '''Put a connection back in the pool.'''
        key = (connection.hostname, connection.port, connection.ssl)
        host_pool = self._pool[key]

        host_pool.check_in(connection)

        if self.count() > self._max_count:
            self.clean(force=True)

    @trollius.coroutine
    def session(self, host, port, ssl=False):
        '''Return a context manager that returns a connection.

        Usage::

            session = yield from connection_pool.session('example.com', 80)
            with session as connection:
                connection.write(b'blah')
                connection.close()

        Coroutine.
        '''
        connection = yield From(self.check_out(host, port, ssl))

        @contextlib.contextmanager
        def context_wrapper():
            try:
                yield connection
            finally:
                self.check_in(connection)

        raise Return(context_wrapper())

    def clean(self, force=False):
        '''Clean all closed connections.'''
        for key, pool in tuple(self._pool.items()):
            pool.clean(force=force)
            if pool.empty():
                del self._pool[key]

    def close(self):
        '''Close all the connections.'''
        for key, pool in tuple(self._pool.items()):
            pool.close()
            del self._pool[key]

    def count(self):
        '''Return number of connections.'''
        counter = 0

        for pool in self._pool.values():
            counter += pool.count()

        return counter

    def _clean_cb(self):
        '''Clean timer callback.'''
        _logger.debug('Periodic connection clean.')

        self.clean()
        trollius.get_event_loop().call_later(120, self._clean_cb)


class ConnectionState(object):
    '''State of a connection

    Attributes:
        ready: Connection is ready to be used
        created: connect has been called successfully
        dead: Connection is closed
    '''
    ready = 'ready'
    created = 'created'
    dead = 'dead'


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
        bandwidth_limiter (class:`.bandwidth.BandwidthLimiter`): Bandwidth
            limiter for connection speed limiting.

    Attributes:
        reader: Stream Reader instance.
        writer: Stream Writer instance.
        address: 2-item tuple containing the IP address.
        host (str): Host name.
        port (int): Port number.
        ssl (bool): Whether connection is SSL.
        tunneled (bool): Whether the connection has been tunneled with the
            ``CONNECT`` request.
    '''
    def __init__(self, address, hostname=None, timeout=None,
                 connect_timeout=None, bind_host=None, bandwidth_limiter=None):
        assert len(address) >= 2, 'Expect str & port. Got {}.'.format(address)
        assert '.' in address[0] or ':' in address[0], \
            'Expect numerical address. Got {}.'.format(address[0])

        self._address = address
        self._hostname = hostname or address[0]
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._bind_host = bind_host
        self._bandwidth_limiter = bandwidth_limiter
        self.reader = None
        self.writer = None
        self._close_timer = None
        self._state = ConnectionState.ready
        self._tunneled = False

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

    @property
    def tunneled(self):
        if self.closed():
            self._tunneled = False

        return self._tunneled

    @tunneled.setter
    def tunneled(self, value):
        self._tunneled = value

    def closed(self):
        '''Return whether the connection is closed.'''
        return not self.writer or not self.reader or self.reader.at_eof()

    def state(self):
        '''Return the state of this connection.'''
        return self._state

    @trollius.coroutine
    def connect(self):
        '''Establish a connection.'''
        _logger.debug(__('Connecting to {0}.', self._address))

        if self._state != ConnectionState.ready:
            raise Exception('Closed connection must be reset before reusing.')

        # TODO: maybe we don't want to ignore flow-info and scope-id?
        host = self._address[0]
        port = self._address[1]

        connection_future = trollius.open_connection(
            host, port, **self._connection_kwargs()
        )
        self.reader, self.writer = yield From(
            self.run_network_operation(
                connection_future,
                wait_timeout=self._connect_timeout,
                name='Connect')
        )

        if self._timeout is not None:
            self._close_timer = CloseTimer(self._timeout, self)
        else:
            self._close_timer = DummyCloseTimer()

        self._state = ConnectionState.created
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
            _logger.debug('Closing connection.')
            self.writer.close()

            self.writer = None
            self.reader = None

        if self._close_timer:
            self._close_timer.close()

        self._state = ConnectionState.dead

    def reset(self):
        '''Prepare connection for reuse.'''
        self.close()
        self._state = ConnectionState.ready

    @trollius.coroutine
    def write(self, data, drain=True):
        '''Write data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        self.writer.write(data)

        if drain:
            fut = self.writer.drain()

            if fut:
                yield From(self.run_network_operation(
                    fut, close_timeout=self._timeout, name='Write')
                )

    @trollius.coroutine
    def read(self, amount=-1):
        '''Read data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        data = yield From(
            self.run_network_operation(
                self.reader.read(amount),
                close_timeout=self._timeout,
                name='Read')
        )

        if self._bandwidth_limiter:
            self._bandwidth_limiter.feed(len(data))

            sleep_time = self._bandwidth_limiter.sleep_time()
            if sleep_time:
                _logger.debug('Sleep %s', sleep_time)
                yield From(trollius.sleep(sleep_time))

        raise Return(data)

    @trollius.coroutine
    def readline(self):
        '''Read a line of data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        with self._close_timer.with_timeout():
            data = yield From(
                self.run_network_operation(
                    self.reader.readline(),
                    close_timeout=self._timeout,
                    name='Readline')
            )

        raise Return(data)

    @trollius.coroutine
    def run_network_operation(self, task, wait_timeout=None,
                              close_timeout=None,
                              name='Network operation'):
        '''Run the task and raise appropriate exceptions.

        Coroutine.
        '''
        if wait_timeout is not None and close_timeout is not None:
            raise Exception(
                'Cannot use wait_timeout and close_timeout at the same time')

        try:
            if close_timeout is not None:
                with self._close_timer.with_timeout():
                    data = yield From(task)

                if self._close_timer.is_timeout():
                    raise NetworkTimedOut(
                        '{name} timed out.'.format(name=name))
                else:
                    raise Return(data)
            elif wait_timeout is not None:
                data = yield From(trollius.wait_for(task, wait_timeout))
                raise Return(data)
            else:
                raise Return((yield From(task)))

        except trollius.TimeoutError as error:
            self.close()
            raise NetworkTimedOut(
                '{name} timed out.'.format(name=name)) from error
        except (tornado.netutil.SSLCertificateError, SSLVerificationError) \
                as error:
            self.close()
            raise SSLVerificationError(
                '{name} certificate error: {error}'
                .format(name=name, error=error)) from error
        except (socket.error, ssl.SSLError, OSError, IOError) as error:
            self.close()
            if isinstance(error, NetworkError):
                raise

            if error.errno == errno.ECONNREFUSED:
                raise ConnectionRefused(
                    error.errno, os.strerror(error.errno)) from error

            # XXX: This quality case brought to you by OpenSSL and Python.
            # Example: _ssl.SSLError: [Errno 1] error:14094418:SSL
            #          routines:SSL3_READ_BYTES:tlsv1 alert unknown ca
            error_string = str(error).lower()
            if 'certificate' in error_string or 'unknown ca' in error_string:
                raise SSLVerificationError(
                    '{name} certificate error: {error}'
                    .format(name=name, error=error)) from error

            else:
                if error.errno:
                    raise NetworkError(
                        error.errno, os.strerror(error.errno)) from error
                else:
                    raise NetworkError(
                        '{name} network error: {error}'
                        .format(name=name, error=error)) from error


class SSLConnection(Connection):
    '''SSL network stream.

    Args:
        ssl_context: SSLContext
    '''
    def __init__(self, *args, ssl_context=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._ssl_context = ssl_context

        if self._ssl_context is True:
            self._ssl_context = tornado.netutil.ssl_options_to_context({})
        elif isinstance(self._ssl_context, dict):
            self._ssl_context = tornado.netutil.ssl_options_to_context(self._ssl_context)

    @property
    def ssl(self):
        return True

    def _connection_kwargs(self):
        kwargs = super()._connection_kwargs()

        if self._ssl_context:
            kwargs['ssl'] = self._ssl_context
            kwargs['server_hostname'] = self._hostname

            return kwargs

    @trollius.coroutine
    def connect(self):
        result = yield From(super().connect())
        sock = self.writer.transport.get_extra_info('socket')
        self._verify_cert(sock)
        raise Return(result)

    def _verify_cert(self, sock):
        # Based on tornado.iostream.SSLIOStream
        # Needed for older Python versions
        verify_mode = self._ssl_context.verify_mode

        assert verify_mode in (ssl.CERT_NONE, ssl.CERT_REQUIRED,
                               ssl.CERT_OPTIONAL), \
            'Unknown verify mode {}'.format(verify_mode)

        if verify_mode == ssl.CERT_NONE:
            return

        cert = sock.getpeercert()

        if cert is None and verify_mode == ssl.CERT_REQUIRED:
            raise SSLVerificationError('No SSL certificate given')

        try:
            tornado.netutil.ssl_match_hostname(cert, self._hostname)
        except SSLCertificateError as error:
            raise SSLVerificationError('Invalid SSL certificate') from error
