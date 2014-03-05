# encoding=utf-8
'''Better torando.iostream.'''
# Some stuff copied from tornado.iostream Copyright 2009 Facebook
import abc
import collections
import datetime
import errno
import logging
import os
import re
import socket
import ssl
import sys
from tornado import stack_context
import tornado.gen
import tornado.ioloop
from tornado.log import gen_log
from tornado.netutil import (ssl_match_hostname, SSLCertificateError,
    ssl_wrap_socket)
import toro

from wpull.errors import NetworkError, SSLVerficationError
from wpull.extended import StreamQueue
from tornado.iostream import StreamClosedError


_logger = logging.getLogger(__name__)
ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)
ERRNO_CONNRESET = (errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE)


class State(object):
    startup = 1
    connecting = 2
    connected = 3
    closed = 4


class BaseIOStream(object, metaclass=abc.ABCMeta):
    """A utility class to write to and read from a non-blocking file or socket.

    We support a non-blocking ``write()`` and a family of ``read_*()`` methods.
    All of the methods take callbacks (since writing and reading are
    non-blocking and asynchronous).

    When a stream is closed due to an error, the IOStream's ``error``
    attribute contains the exception object.

    Subclasses must implement `fileno`, `close_fd`, `write_to_fd`,
    `read_from_fd`, and optionally `get_fd_error`.
    """
    def __init__(self, io_loop=None, max_buffer_size=10485760,
    read_chunk_size=4096, connect_timeout=None, read_timeout=None,
    write_timeout=None):
        super().__init__()
        self._io_loop = io_loop or tornado.ioloop.IOLoop.current()
        self._max_buffer_size = max_buffer_size
        self._read_chunk_size = read_chunk_size

        if connect_timeout is not None:
            self._connect_timeout = datetime.timedelta(seconds=connect_timeout)
        else:
            self._connect_timeout = None

        if read_timeout is not None:
            self._read_timeout = datetime.timedelta(seconds=read_timeout)
        else:
            self._read_timeout = None

        if write_timeout is not None:
            self._write_timeout = datetime.timedelta(seconds=write_timeout)
        else:
            self._write_timeout = None

        self._state = State.startup
        self._local_read_queue = collections.deque()
        self._read_queue = toro.Queue(maxsize=10, io_loop=self._io_loop)
        self._write_queue = toro.Queue(io_loop=self._io_loop)
        self._read_event = toro.Condition(io_loop=self._io_loop)
        self._write_event = toro.Condition(io_loop=self._io_loop)
#         self._error_event = toro.Condition(io_loop=self._io_loop)
        self._close_callback = None
        self.error = None

    @property
    def reading(self):
        # TODO:
        pass

    @property
    def writing(self):
        # TODO:
        pass

    @property
    def closed(self):
        return self._state == State.closed

    @abc.abstractmethod
    def fileno(self):
        """Returns the file descriptor for this stream."""
        pass

    @abc.abstractmethod
    def _close_fd(self):
        """Closes the file underlying this stream."""
        pass

    @abc.abstractmethod
    def _write_to_fd(self, data):
        """Attempts to write ``data`` to the underlying file.

        Returns the number of bytes written.
        """
        pass

    @abc.abstractmethod
    def _read_from_fd(self):
        """Attempts to read from the underlying file.

        Returns ``None`` if there was nothing to read (the socket
        returned `~errno.EWOULDBLOCK` or equivalent), otherwise
        returns the data.  When possible, should return no more than
        ``self.read_chunk_size`` bytes at a time.
        """
        pass

    def get_fd_error(self):
        """Returns information about any error on the underlying file.

        This method is called after the `.IOLoop` has signaled an error on the
        file descriptor, and should return an Exception (such as `socket.error`
        with additional information, or None if no such information is
        available.
        """
        return None

    @tornado.gen.coroutine
    def read_until_regex(self, regex):
        """Run ``callback`` when we read the given regex pattern.

        The callback will get the data read (including the data that
        matched the regex and anything that came before it) as an argument.
        """
        chunk_buffer = collections.deque()
        buffer_size = 0

        while True:
            data = yield self.read_bytes(self._read_chunk_size)
            match = re.search(regex, data)

            if match:
                chunk_buffer.append(data[:match.end()])
                self._local_read_queue.appendleft(data[match.end():])
                raise tornado.gen.Return(b''.join(chunk_buffer))

            buffer_size += len(data)

            if buffer_size > self._max_buffer_size:
                raise ValueError('Buffer size exceeded.')

            chunk_buffer.append(data)
            double_prefix(chunk_buffer)

    @tornado.gen.coroutine
    def read_until(self, delimiter):
        """Run ``callback`` when we read the given delimiter.

        The callback will get the data read (including the delimiter)
        as an argument.
        """
        chunk_buffer = collections.deque()
        buffer_size = 0

        while True:
            data = yield self.read_bytes(self._read_chunk_size)
            loc = data.find(delimiter)

            if loc != -1:
                chunk_buffer.append(data[:loc + 1])
                self._local_read_queue.appendleft(data[loc + 1:])
                raise tornado.gen.Return(b''.join(chunk_buffer))

            buffer_size += len(data)

            if buffer_size > self._max_buffer_size:
                raise ValueError('Buffer size exceeded.')

            chunk_buffer.append(data)
            double_prefix(chunk_buffer)

    @tornado.gen.coroutine
    def read_bytes(self, num_bytes, streaming_callback=None):
        """Run callback when we read the given number of bytes.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the argument to the final
        ``callback`` will be empty.  Otherwise, the ``callback`` gets
        the data as an argument.
        """
        assert self._state == State.connected

        bulk_data = []
        bytes_left = num_bytes if num_bytes is not None else True

        while len(self._local_read_queue) and bytes_left:
            data = self._local_read_queue.popleft()

            if num_bytes is not None:
                if len(data) > bytes_left:
                    self._local_read_queue.appendleft(data[bytes_left:])
                    data = data[:bytes_left]

                bytes_left = num_bytes - len(data)

            if streaming_callback is not None:
                streaming_callback(data)
            else:
                bulk_data.append(data)

        while not self.closed and bytes_left:
            data = yield self._read_queue.get(self._read_timeout)

            if not data:
                break

            if num_bytes is not None:
                if len(data) > bytes_left:
                    self._local_read_queue.append(data[bytes_left:])
                    data = data[:bytes_left]

                bytes_left = num_bytes - len(data)

            if streaming_callback is not None:
                streaming_callback(data)
            else:
                bulk_data.append(data)

        if streaming_callback is None:
            raise tornado.gen.Return(b''.join(bulk_data))

    @tornado.gen.coroutine
    def read_until_close(self, streaming_callback=None):
        """Reads all data from the socket until it is closed.

        If a ``streaming_callback`` is given, it will be called with chunks
        of data as they become available, and the argument to the final
        ``callback`` will be empty.  Otherwise, the ``callback`` gets the
        data as an argument.

        Subject to ``max_buffer_size`` limit from `IOStream` constructor if
        a ``streaming_callback`` is not used.
        """
        raise tornado.gen.Return(
            (yield self.read_bytes(None, streaming_callback))
        )

    def read_bytes_queue(self, num_bytes):
        '''Read with queue.

        Returns:
            StreamQueue: An instance of `.extended.StreamQueue`.
        '''
        return self._read_with_queue(self.read_bytes, num_bytes)

    def read_until_close_queue(self):
        '''Read until close with queue.

        Returns:
            StreamQueue: An instance of `.extended.StreamQueue`.
        '''
        return self._read_with_queue(self.read_until_close)

    def _read_with_queue(self, read_function, *args, **kwargs):
        '''Read with timeout and queue.'''
        stream_queue = StreamQueue(deadline=self._read_timeout)

        def callback(data):
            stream_queue.put_nowait(None)

        def stream_callback(data):
            stream_queue.put_nowait(data)

        read_function(
            *args,
            callback=callback,
            streaming_callback=stream_callback,
            **kwargs
        )

        return stream_queue

    @tornado.gen.coroutine
    def write(self, data):
        """Write the given data to this stream."""
        yield self._write_queue.put(data, deadline=self._write_timeout)

    def set_close_callback(self, callback):
        """Call the given callback when the stream is closed."""
        self._close_callback = stack_context.wrap(callback)

    def close(self, exc_info=False):
        """Close this stream."""
        if not self.closed:
            _logger.debug('Closing stream.')

            if exc_info:
                _logger.debug('Close with exc.')
                if not isinstance(exc_info, tuple):
                    exc_info = sys.exc_info()
                if any(exc_info):
                    self.error = exc_info[1]

            self._io_loop.remove_handler(self.fileno())
            self._close_fd()
            self._read_queue.put(None)
            self._run_close_callback()

        self._state = State.closed

    def _run_close_callback(self):
        if self._close_callback is None:
            return

        _logger.debug('Running callback.')

        try:
            self._close_callback()
        except Exception:
            _logger.exception('Error on close callback.')
            self.close(exc_info=True)
            raise
        finally:
            self._close_callback = None

    def _start(self):
        '''Start event handler and IO loops.'''
        _logger.debug('Starting handler and loops.')
        self._io_loop.add_handler(
            self.fileno(), self._event_handler,
            self._io_loop.READ | self._io_loop.WRITE | self._io_loop.ERROR
        )
        self._io_loop.add_future(self._read_loop(), self._loop_end_handler)
        self._io_loop.add_future(self._write_loop(), self._loop_end_handler)

    def _event_handler(self, fd, events):
        '''Event handler.'''
        if events & tornado.ioloop.IOLoop.READ:
            self._read_event.notify_all()

        if events & tornado.ioloop.IOLoop.WRITE:
            self._write_event.notify_all()

        if events & tornado.ioloop.IOLoop.ERROR:
            _logger.debug('FD events {0}'.format(events))
            self.error = self.get_fd_error()
            self.close()

    def _loop_end_handler(self, future):
        '''Event handler when loop futures end.'''
        try:
            future.result()
        except Exception:
            _logger.exception('Loop ended.')
            self.close(exc_info=True)
            raise

    @tornado.gen.coroutine
    def _read_loop(self):
        '''Loop that reads from FD.'''
        while not self.closed:
            yield self._read_event.wait()
            data = self._read_from_fd()
            yield self._read_queue.put(data)

    @tornado.gen.coroutine
    def _write_loop(self):
        '''Loop that writes to FD.'''
        iterative_queue = collections.deque()

        while not self.closed:
            yield self._write_event.wait(deadline=self._write_timeout)

            if len(iterative_queue):
                data = iterative_queue.popleft()
            else:
                data = yield self._write_queue.get()

            try:
                self._write_to_fd(data)
            except (socket.error, IOError, OSError) as error:
                if error.args[0] in ERRNO_WOULDBLOCK:
                    iterative_queue.appendleft(data)
                else:
                    raise


class IOStream(BaseIOStream):
    """Socket-based `IOStream` implementation.

    This class supports the read and write methods from `BaseIOStream`
    plus a `connect` method.

    The ``socket`` parameter may either be connected or unconnected.
    For server operations the socket is the result of calling
    `socket.accept <socket.socket.accept>`.  For client operations the
    socket is created with `socket.socket`, and may either be
    connected before passing it to the `IOStream` or connected with
    `IOStream.connect`.
    """
    def __init__(self, socket_, *args, **kwargs):
        self.socket = socket_
        self.socket.setblocking(False)
        super().__init__(*args, **kwargs)

    def fileno(self):
        return self.socket.fileno()

    def _close_fd(self):
        self.socket.close()
        self.socket = None

    def get_fd_error(self):
        errno_ = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        return socket.error(errno_, os.strerror(errno_))

    def _read_from_fd(self):
        try:
            chunk = self.socket.recv(self._read_chunk_size)
        except socket.error as error:
            if error.args[0] in ERRNO_WOULDBLOCK:
                return None
            else:
                raise
        if not chunk:
            self.close()
            return None
        return chunk

    def _write_to_fd(self, data):
        return self.socket.send(data)

    @tornado.gen.coroutine
    def connect(self, address, server_hostname=None):
        """Connects the socket to a remote address without blocking.

        May only be called if the socket passed to the constructor was
        not previously connected.  The address parameter is in the
        same format as for `socket.connect <socket.socket.connect>`,
        i.e. a ``(host, port)`` tuple.  If ``callback`` is specified,
        it will be called when the connection is completed.

        If specified, the ``server_hostname`` parameter will be used
        in SSL connections for certificate validation (if requested in
        the ``ssl_options``) and SNI (if supported; requires
        Python 3.2+).

        Note that it is safe to call `IOStream.write
        <BaseIOStream.write>` while the connection is pending, in
        which case the data will be written as soon as the connection
        is ready.  Calling `IOStream` read methods before the socket is
        connected works on some platforms but is non-portable.
        """
        self._state = State.connecting

        try:
            self.socket.connect(address)
        except socket.error as e:
            if (e.args[0] != errno.EINPROGRESS and
                    e.args[0] not in ERRNO_WOULDBLOCK):
                self.close()
                raise

        _logger.debug('Connecting.')

        try:
            yield wait_events(
                self._io_loop, self.socket.fileno(), self._io_loop.WRITE,
                deadline=self._connect_timeout
            )
        except toro.Timeout:
            self.close()
            raise NetworkError('Connection timed out.')

        self._handle_connect()
        self._start()

    def _handle_connect(self):
        err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            error = socket.error(err, os.strerror(err))
            self.close()
            raise error

        self._state = State.connected

        _logger.debug('Connected.')


class SSLIOStream(IOStream):
    """A utility class to write to and read from a non-blocking SSL socket.

    If the socket passed to the constructor is already connected,
    it should be wrapped with::

        ssl.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)

    before constructing the `SSLIOStream`.  Unconnected sockets will be
    wrapped when `IOStream.connect` is finished.
    """
    def __init__(self, *args, **kwargs):
        """The ``ssl_options`` keyword argument may either be a dictionary
        of keywords arguments for `ssl.wrap_socket`, or an `ssl.SSLContext`
        object.
        """
        self._ssl_options = kwargs.pop('ssl_options', {})
        super().__init__(*args, **kwargs)
        self._ssl_accepting = True
        self._handshake_reading = False
        self._handshake_writing = False
        self._ssl_connect_callback = None
        self._server_hostname = None

        # If the socket is already connected, attempt to start the handshake.
        try:
            self.socket.getpeername()
        except socket.error:
            pass

    def _do_ssl_handshake(self):
        # Based on code from test_ssl.py in the python stdlib
        try:
            self._handshake_reading = False
            self._handshake_writing = False
            self.socket.do_handshake()
        except ssl.SSLError as err:
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self._handshake_reading = True
                return
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self._handshake_writing = True
                return
            elif err.args[0] in (ssl.SSL_ERROR_EOF,
                                 ssl.SSL_ERROR_ZERO_RETURN):
                return self.close()
            elif err.args[0] == ssl.SSL_ERROR_SSL:
                self.socket.getpeername()

            raise
        except socket.error as err:
            if err.args[0] in ERRNO_CONNRESET:
                raise
        except AttributeError:
            # On Linux, if the connection was reset before the call to
            # wrap_socket, do_handshake will fail with an
            # AttributeError.
            raise
        else:
            self._ssl_accepting = False
            self._verify_cert(self.socket.getpeercert())

    def _verify_cert(self, peercert):
        """Returns True if peercert is valid according to the configured
        validation mode and hostname.

        The ssl handshake already tested the certificate for a valid
        CA signature; the only thing that remains is to check
        the hostname.
        """
        if isinstance(self._ssl_options, dict):
            verify_mode = self._ssl_options.get('cert_reqs', ssl.CERT_NONE)
        elif isinstance(self._ssl_options, ssl.SSLContext):
            verify_mode = self._ssl_options.verify_mode

        assert verify_mode in (ssl.CERT_NONE, ssl.CERT_REQUIRED,
            ssl.CERT_OPTIONAL)

        if verify_mode == ssl.CERT_NONE or self._server_hostname is None:
            return True

        cert = self.socket.getpeercert()

        if cert is None and verify_mode == ssl.CERT_REQUIRED:
            raise SSLVerficationError("No SSL certificate given")

        try:
            ssl_match_hostname(peercert, self._server_hostname)
        except SSLCertificateError as error:
            raise SSLVerficationError("Hostname could not be verified.") \
                from error

    @tornado.gen.coroutine
    def connect(self, address, server_hostname=None):
        # Save the user's callback and run it after the ssl handshake
        # has completed.
        self._server_hostname = server_hostname
        yield super().connect(address, callback=None)

        self.socket = ssl_wrap_socket(self.socket, self._ssl_options,
                                      server_hostname=self._server_hostname,
                                      do_handshake_on_connect=False)

        while self._ssl_accepting:
            yield [self._write_event, self._read_event]

            try:
                self._do_ssl_handshake()
            except:
                self.close(exc_info=True)
                raise

    def read_from_fd(self):
        if self._ssl_accepting:
            return None

        try:
            chunk = self.socket.read(self._read_chunk_size)
        except ssl.SSLError as e:
            if e.args[0] == ssl.SSL_ERROR_WANT_READ:
                return None
            else:
                raise
        except socket.error as e:
            if e.args[0] in ERRNO_WOULDBLOCK:
                return None
            else:
                raise

        if not chunk:
            self.close()
            return None

        return chunk


@tornado.gen.coroutine
def wait_events(io_loop, fd, events, clear=True, deadline=None):
    async_result = toro.AsyncResult()

    def handler(fd, events):
        async_result.set(events)

    io_loop.add_handler(fd, handler, events)

    try:
        events = yield async_result.get(deadline)
    finally:
        if clear:
            io_loop.remove_handler(fd)

    raise tornado.gen.Return(events)


def double_prefix(deque):
    """Grow by doubling, but don't split the second chunk just because the
    first one is small.
    """
    new_len = max(len(deque[0]) * 2,
                  (len(deque[0]) + len(deque[1])))
    merge_prefix(deque, new_len)


def merge_prefix(deque, size):
    """Replace the first entries in a deque of strings with a single
    string of up to size bytes.

    ::

        >>> d = collections.deque(['abc', 'de', 'fghi', 'j'])
        >>> merge_prefix(d, 5); print(d)
        deque(['abcde', 'fghi', 'j'])

    Strings will be split as necessary to reach the desired size.::

        >>> merge_prefix(d, 7); print(d)
        deque(['abcdefg', 'hi', 'j'])

        >>> merge_prefix(d, 3); print(d)
        deque(['abc', 'defg', 'hi', 'j'])

        >>> merge_prefix(d, 100); print(d)
        deque(['abcdefghij'])
    """
    if len(deque) == 1 and len(deque[0]) <= size:
        return
    prefix = []
    remaining = size
    while deque and remaining > 0:
        chunk = deque.popleft()
        if len(chunk) > remaining:
            deque.appendleft(chunk[remaining:])
            chunk = chunk[:remaining]
        prefix.append(chunk)
        remaining -= len(chunk)
    # This data structure normally just contains byte strings, but
    # the unittest gets messy if it doesn't use the default str() type,
    # so do the merge based on the type of data that's actually present.
    if prefix:
        deque.appendleft(type(prefix[0])().join(prefix))
    if not deque:
        deque.appendleft(b"")
