# encoding=utf8
'''Network connections.'''
import asyncio
import contextlib
import enum
import errno
import logging
import os
import socket
import ssl

import tornado.netutil
from tornado.netutil import SSLCertificateError
from typing import Optional, Union
from wpull.backport.logging import BraceMessage as __
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
        self._event_loop = asyncio.get_event_loop()
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

    def is_timeout(self) -> bool:
        '''Return whether the timer has timed out.'''
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


class ConnectionState(enum.Enum):
    '''State of a connection

    Attributes:
        ready: Connection is ready to be used
        created: connect has been called successfully
        dead: Connection is closed
    '''
    ready = 'ready'
    created = 'created'
    dead = 'dead'


class BaseConnection(object):
    '''Base network stream.

    Args:
        address: 2-item tuple containing the IP address and port or 4-item
            for IPv6.
        hostname: Hostname of the address (for SSL).
        timeout: Time in seconds before a read/write operation times out.
        connect_timeout: Time in seconds before a connect operation times out.
        bind_host: Host name for binding the socket interface.
        sock: Use given socket. The socket must already by connected.

    Attributes:
        reader: Stream Reader instance.
        writer: Stream Writer instance.
        address: 2-item tuple containing the IP address.
        host: Host name.
        port: Port number.
    '''
    def __init__(self, address: tuple, hostname: Optional[str]=None,
                 timeout: Optional[float]=None,
                 connect_timeout: Optional[float]=None,
                 bind_host: Optional[str]=None,
                 sock: Optional[socket.socket]=None):
        assert len(address) >= 2, 'Expect str & port. Got {}.'.format(address)
        assert '.' in address[0] or ':' in address[0], \
            'Expect numerical address. Got {}.'.format(address[0])

        self._address = address
        self._hostname = hostname or address[0]
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._bind_host = bind_host
        self._sock = sock
        self.reader = None
        self.writer = None
        self._close_timer = None
        self._state = ConnectionState.ready

    @property
    def address(self) -> tuple:
        return self._address

    @property
    def hostname(self) -> Optional[str]:
        return self._hostname

    @property
    def host(self) -> str:
        return self._address[0]

    @property
    def port(self) -> int:
        return self._address[1]

    def closed(self) -> bool:
        '''Return whether the connection is closed.'''
        return not self.writer or not self.reader or self.reader.at_eof()

    def state(self) -> ConnectionState:
        '''Return the state of this connection.'''
        return self._state

    @asyncio.coroutine
    def connect(self):
        '''Establish a connection.'''
        _logger.debug(__('Connecting to {0}.', self._address))

        if self._state != ConnectionState.ready:
            raise Exception('Closed connection must be reset before reusing.')

        if self._sock:
            connection_future = asyncio.open_connection(
                sock=self._sock, **self._connection_kwargs()
            )
        else:
            # TODO: maybe we don't want to ignore flow-info and scope-id?
            host = self._address[0]
            port = self._address[1]

            connection_future = asyncio.open_connection(
                host, port, **self._connection_kwargs()
            )

        self.reader, self.writer = yield from \
            self.run_network_operation(
                connection_future,
                wait_timeout=self._connect_timeout,
                name='Connect')

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

    @asyncio.coroutine
    def write(self, data: bytes, drain: bool=True):
        '''Write data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        self.writer.write(data)

        if drain:
            fut = self.writer.drain()

            if fut:
                yield from self.run_network_operation(
                    fut, close_timeout=self._timeout, name='Write')

    @asyncio.coroutine
    def read(self, amount: int=-1) -> bytes:
        '''Read data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        data = yield from \
            self.run_network_operation(
                self.reader.read(amount),
                close_timeout=self._timeout,
                name='Read')

        return data

    @asyncio.coroutine
    def readline(self) -> bytes:
        '''Read a line of data.'''
        assert self._state == ConnectionState.created, \
            'Expect conn created. Got {}.'.format(self._state)

        with self._close_timer.with_timeout():
            data = yield from \
                self.run_network_operation(
                    self.reader.readline(),
                    close_timeout=self._timeout,
                    name='Readline')

        return data

    @asyncio.coroutine
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
                    data = yield from task

                if self._close_timer.is_timeout():
                    raise NetworkTimedOut(
                        '{name} timed out.'.format(name=name))
                else:
                    return data
            elif wait_timeout is not None:
                data = yield from asyncio.wait_for(task, wait_timeout)
                return data
            else:
                return (yield from task)

        except asyncio.TimeoutError as error:
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


class Connection(BaseConnection):
    '''Network stream.

    Args:
        bandwidth_limiter (class:`.bandwidth.BandwidthLimiter`): Bandwidth
            limiter for connection speed limiting.

    Attributes:
        key: Value used by the ConnectionPool for its host pool map. Internal
            use only.
        wrapped_connection: A wrapped connection for ConnectionPool. Internal
            use only.

        is_ssl (bool): Whether connection is SSL.
        proxied (bool): Whether the connection is to a HTTP proxy.
        tunneled (bool): Whether the connection has been tunneled with the
            ``CONNECT`` request.
    '''
    def __init__(self, *args, bandwidth_limiter=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._bandwidth_limiter = bandwidth_limiter
        self.key = None
        self.wrapped_connection = None
        self._proxied = False
        self._tunneled = False

    @property
    def is_ssl(self) -> bool:
        return False

    @property
    def tunneled(self) -> bool:
        if self.closed():
            self._tunneled = False

        return self._tunneled

    @tunneled.setter
    def tunneled(self, value):
        self._tunneled = value

    @property
    def proxied(self) -> bool:
        return self._proxied

    @proxied.setter
    def proxied(self, value):
        self._proxied = value

    @asyncio.coroutine
    def read(self, amount: int=-1) -> bytes:
        data = yield from super().read(amount)

        if self._bandwidth_limiter:
            self._bandwidth_limiter.feed(len(data))

            sleep_time = self._bandwidth_limiter.sleep_time()
            if sleep_time:
                _logger.debug('Sleep %s', sleep_time)
                yield from asyncio.sleep(sleep_time)

        return data

    @asyncio.coroutine
    def start_tls(self, ssl_context: Union[bool, dict, ssl.SSLContext]=True) \
            -> 'SSLConnection':
        '''Start client TLS on this connection and return SSLConnection.

        Coroutine
        '''
        sock = self.writer.get_extra_info('socket')
        ssl_conn = SSLConnection(
            self._address,
            ssl_context=ssl_context,
            hostname=self._hostname, timeout=self._timeout,
            connect_timeout=self._connect_timeout, bind_host=self._bind_host,
            bandwidth_limiter=self._bandwidth_limiter, sock=sock
        )

        yield from ssl_conn.connect()

        return ssl_conn


class SSLConnection(Connection):
    '''SSL network stream.

    Args:
        ssl_context: SSLContext
    '''
    def __init__(self, *args,
                 ssl_context: Union[bool, dict, ssl.SSLContext]=True, **kwargs):
        super().__init__(*args, **kwargs)
        self._ssl_context = ssl_context

        if self._ssl_context is True:
            self._ssl_context = tornado.netutil.ssl_options_to_context({})
        elif isinstance(self._ssl_context, dict):
            self._ssl_context = tornado.netutil.ssl_options_to_context(
                self._ssl_context)

    @property
    def is_ssl(self) -> bool:
        return True

    def _connection_kwargs(self):
        kwargs = super()._connection_kwargs()

        if self._ssl_context:
            kwargs['ssl'] = self._ssl_context
            kwargs['server_hostname'] = self._hostname

            return kwargs

    @asyncio.coroutine
    def connect(self):
        result = yield from super().connect()
        sock = self.writer.transport.get_extra_info('ssl_object', self.writer.transport.get_extra_info('socket'))
        self._verify_cert(sock)
        return result

    def _verify_cert(self, sock: ssl.SSLSocket):
        '''Check if certificate matches hostname.'''
        # Based on tornado.iostream.SSLIOStream
        # Needed for older OpenSSL (<0.9.8f) versions
        verify_mode = self._ssl_context.verify_mode

        assert verify_mode in (ssl.CERT_NONE, ssl.CERT_REQUIRED,
                               ssl.CERT_OPTIONAL), \
            'Unknown verify mode {}'.format(verify_mode)

        if verify_mode == ssl.CERT_NONE:
            return

        cert = sock.getpeercert()

        if not cert and verify_mode == ssl.CERT_OPTIONAL:
            return

        if not cert:
            raise SSLVerificationError('No SSL certificate given')

        try:
            ssl.match_hostname(cert, self._hostname)
        except ssl.CertificateError as error:
            raise SSLVerificationError('Invalid SSL certificate') from error
