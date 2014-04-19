# encoding=utf-8
'''Socket streams.'''
import collections
import datetime
import errno
import gettext
import logging
import os
import re
import socket
import ssl

import tornado.gen
import tornado.ioloop
from tornado.iostream import StreamClosedError
import tornado.netutil
import tornado.stack_context
import toro

from wpull.errors import (NetworkError, SSLVerficationError, NetworkTimedOut,
    ConnectionRefused)


WRITE = tornado.ioloop.IOLoop.WRITE
READ = tornado.ioloop.IOLoop.READ
ERROR = tornado.ioloop.IOLoop.ERROR
_ = gettext.gettext
_logger = logging.getLogger(__name__)


class State(object):
    '''Connection states.

    Attributes:
        not_yet_connected (1): Not yet connected.
        connecting (2): Connecting.
        connected (3): Connected.
        closed (4): Closed.
        wait_for_close (5): Waiting for remote to close.
    '''
    not_yet_connected = 1
    connecting = 2
    connected = 3
    closed = 4
    wait_for_close = 5


class BufferFullError(ValueError):
    '''Exception for :class:`DataBuffer` when the buffer is full.'''


class DataBuffer(object):
    '''A growing data buffer.

    Args:
        max_size (int): The maximum number of bytes to store.

    This buffer uses algorithms similar to :mod:`tornado.iostream`.
    '''
    def __init__(self, max_size=1048576):
        self._data = collections.deque()
        self._num_bytes = 0
        self._max_size = max_size

    @property
    def num_bytes(self):
        '''The number of bytes in the buffer.'''
        return self._num_bytes

    def get_bytes(self, length):
        '''Return the data up to `length` bytes.'''
        if not self._data:
            return b''

        item = self._data.popleft()

        data, item = item[:length], item[length:]
        self._num_bytes -= len(data)

        if item:
            self._data.appendleft(item)

        return data

    def get_until_delim(self, delim):
        '''Return the data up to and including the delimiter.

        Args:
            delim (bytes): The delimiter.
        '''
        while self._data:
            first_item = self._data[0]

            try:
                index = first_item.index(delim) + len(delim)
            except ValueError:
                if self.is_wranglable():
                    self.wrangle()
                else:
                    break
            else:
                self._data.popleft()

                item_1, item_2 = first_item[:index], first_item[index:]
                self._num_bytes -= len(item_1)

                if item_2:
                    self._data.appendleft(item_2)

                return item_1

        return b''

    def get_until_regex(self, pattern):
        '''Return the data up to and including the match.

        Args:
            pattern (bytes, compiled regex object): The pattern.
        '''
        while self._data:
            first_item = self._data[0]
            match = re.search(pattern, first_item)

            if match:
                self._data.popleft()

                index = match.end()
                item_1, item_2 = first_item[:index], first_item[index:]
                self._num_bytes -= len(item_1)

                if item_2:
                    self._data.appendleft(item_2)

                return item_1
            else:
                if self.is_wranglable():
                    self.wrangle()
                else:
                    break

        return b''

    def put(self, data):
        '''Put data into the buffer.

        Args:
            data (bytes): The data. Must not be empty.
        '''
        assert data

        self._num_bytes += len(data)

        if self._num_bytes > self._max_size:
            raise BufferFullError('Buffer is full.')

        self._data.append(data)

    def is_wranglable(self):
        '''Return whether the internal buffer can be wrangled.'''
        return len(self._data) >= 2

    def wrangle(self):
        '''Join the internal data parts into larger parts.'''
        if not self.is_wranglable():
            return

        first_item = self._data.popleft()
        items = [first_item]
        chomp_remain = len(first_item)

        while self._data and chomp_remain > 0:
            item = self._data.popleft()
            chomp_remain -= len(item)

            assert item

            items.append(item)

        item = b''.join(items)

        self._data.appendleft(item)

    def has_data(self):
        '''Return whether the buffer contains data.'''
        return len(self._data) != 0


class IOStream(object):
    '''Socket IO Stream.

    Args:
        socket_obj: A socket object. If the socket is connected, call
            :meth:`attach` before reading or writing. Otherwise,
            call :meth:`connect`.
        ioloop: IOLoop.
        chunk_size (int): The number of bytes read per receive call.
        max_buffer_size (int): Maximum size of the buffer in bytes.
        rw_timeout (float): Timeout in seconds for reads and writes.
    '''
    def __init__(self, socket_obj, ioloop=None, chunk_size=4096,
    max_buffer_size=1048576, rw_timeout=None):
        self._socket = socket_obj
        self._ioloop = ioloop or tornado.ioloop.IOLoop.current()
        self._chunk_size = chunk_size
        self._rw_timeout = rw_timeout

        self._state = State.not_yet_connected
        self._event_result = None
        self._data_buffer = DataBuffer(max_size=max_buffer_size)
        self._stream_closed_callback = None
        self._blocking_counter = 0

    @property
    def socket(self):
        '''The socket.'''
        return self._socket

    @property
    def state(self):
        '''The current state defined in :class:`State`.'''
        return self._state

    def closed(self):
        '''Return whether the stream is closed.'''
        return self._state == State.closed

    def _handle_socket(self):
        '''Add the socket to the IO loop handler.'''
        self._ioloop.add_handler(self._socket.fileno(), self._event_handler, 0)

    def _remove_handler(self):
        '''Remove the socket from the IO loop handler.'''
        self._ioloop.remove_handler(self._socket.fileno())

    def _event_handler(self, fd, events):
        '''Handle and set the async result and clear the event listener.'''
        self._update_handler(0)

        if self._state == State.wait_for_close:
            self.check_socket_closed()
        elif self._event_result and not self._event_result.ready():
            self._event_result.set(events)
        else:
            _logger.debug(
                'Spurious events: FD={0} Events=0x{1:x}.'.format(fd, events)
            )

    @tornado.gen.coroutine
    def _wait_event(self, events, timeout=None):
        '''Set the events to listen for and wait for it to occur.'''
        assert self._state != State.not_yet_connected

        deadline = datetime.timedelta(seconds=timeout) if timeout else None
        self._event_result = toro.AsyncResult()

        self._update_handler(events)

        try:
            events = yield self._event_result.get(deadline)
        except toro.Timeout as error:
            msg = 'Connection timed out (Events: 0x{events_code:x}).'

            if events & READ and not events & WRITE:
                msg = 'Read timed out (Events: 0x{events_code:x}).'
            elif events & WRITE and not events & READ:
                msg = 'Write timed out (Events: 0x{events_code:x}).'

            raise NetworkTimedOut(msg.format(events_code=events)) from error

        raise tornado.gen.Return(events)

    def _update_handler(self, events):
        '''Update the IOLoop events to listen for.'''
        try:
            self._ioloop.update_handler(self._socket.fileno(), events)
        except (OSError, IOError) as error:
            self.close()
            raise NetworkError(
                'Failed to update handler: {error}'.format(error=error)
                ) from error

    def _raise_socket_error(self):
        '''Get the error from the socket and raise an error.'''
        error_code = self._socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_ERROR
            )

        self.close()

        if error_code == errno.ECONNREFUSED:
            raise ConnectionRefused(error_code, os.strerror(error_code))
        else:
            raise NetworkError(error_code, os.strerror(error_code))

    def close(self):
        '''Close the socket.'''
        if self._state == State.closed:
            return

        _logger.debug('Stream closing.')

        self._state = State.closed
        self._remove_handler()
        self._socket.close()

        if self._stream_closed_callback:
            self._stream_closed_callback()
            self._stream_closed_callback = None

    @tornado.gen.coroutine
    def connect(self, address, timeout=None):
        '''Connect the socket.

        Args:
            address (tuple): An address passed to the socket connect function.
                Typical values are the IP address and port number.
            timeout (float): A timeout value in seconds.
        '''
        if self._state != State.not_yet_connected:
            raise IOError('Stream already connected or closed.')

        self._socket.setblocking(0)
        self._handle_socket()

        self._state = State.connected

        try:
            self._socket.connect(address)
        except IOError as error:
            if error.errno not in (errno.EWOULDBLOCK, errno.EINPROGRESS):
                raise

        try:
            events = yield self._wait_event(
                READ | WRITE | ERROR, timeout=timeout
            )
        except NetworkTimedOut:
            self.close()
            raise

        if events & ERROR:
            self._raise_socket_error()

    def attach(self):
        '''Set up with an already connected socket.'''
        self._remove_handler()
        self._handle_socket()
        self._state = State.connected

    @tornado.gen.coroutine
    def write(self, data):
        '''Write all data to socket.

        This function uses a blocking fast path consecutively for
        every 100 writes.
        '''
        self.stop_monitor_for_close()

        total_bytes_sent = 0

        while total_bytes_sent < len(data):
            if self._blocking_counter < 100:
                try:
                    bytes_sent = self._socket.send(data[total_bytes_sent:])
                except ssl.SSLError as error:
                    if error.errno != ssl.SSL_ERROR_WANT_WRITE:
                        raise
                except IOError as error:
                    if error.errno not in (
                    errno.EWOULDBLOCK, errno.EINPROGRESS):
                        raise
                else:
                    if not bytes_sent:
                        self.close()
                        raise StreamClosedError('Stream unexpectedly closed.')
                    else:
                        total_bytes_sent += bytes_sent
                        continue
            else:
                self._blocking_counter = 0

            events = yield self._wait_event(
                WRITE | ERROR, timeout=self._rw_timeout
            )

            if events & ERROR:
                self._raise_socket_error()

            bytes_sent = self._socket.send(data[total_bytes_sent:])

            if not bytes_sent:
                self.close()
                raise StreamClosedError('Stream unexpectedly closed.')

            total_bytes_sent += bytes_sent

    @tornado.gen.coroutine
    def read(self, length):
        '''Read from socket.

        This function reads only from the socket and not the buffer.

        This function uses a blocking fast path consecutively for
        every 100 reads.
        '''
        self.stop_monitor_for_close()

        if self._blocking_counter < 100:
            try:
                data = self._socket.recv(length)
            except ssl.SSLError as error:
                if error.errno != ssl.SSL_ERROR_WANT_READ:
                    raise
            except IOError as error:
                if error.errno not in (errno.EWOULDBLOCK, errno.EINPROGRESS):
                    raise
            else:
                if data:
                    self._blocking_counter += 1
                    raise tornado.gen.Return(data)
                else:
                    self.close()
                    raise StreamClosedError('Stream unexpectedly closed.')
        else:
            self._blocking_counter = 0

        while True:
            events = yield self._wait_event(
                READ | ERROR, timeout=self._rw_timeout
            )

            if events & ERROR:
                self._raise_socket_error()

            try:
                data = self._socket.recv(length)
            except ssl.SSLError as error:
                if error.errno == ssl.SSL_ERROR_WANT_READ:
                    continue
                else:
                    raise
            else:
                break

        if not data:
            self.close()
            raise StreamClosedError('Stream unexpectedly closed.')

        raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_bytes(self, length, streaming_callback=None):
        '''Read exactly `length` bytes from the socket or buffer.

        Args:
            length (int): Number of bytes to read.
            streaming_callback: A callback function that receives data.

        Returns:
            bytes,None
        '''
        bytes_left = length

        if not streaming_callback:
            data_list = []

        while bytes_left > 0:
            if self._data_buffer.has_data():
                data = self._data_buffer.get_bytes(length)
            else:
                data = yield self.read(min(bytes_left, self._chunk_size))

            bytes_left -= len(data)

            if streaming_callback:
                streaming_callback(data)
            else:
                data_list.append(data)

        assert bytes_left == 0

        if streaming_callback:
            raise tornado.gen.Return(None)
        else:
            raise tornado.gen.Return(b''.join(data_list))

    @tornado.gen.coroutine
    def read_until(self, delimiter):
        '''Read until a delimiter from socket or buffer.

        Returns:
            bytes: The data including the delimiter.
        '''
        data = self._data_buffer.get_until_delim(delimiter)

        if data:
            raise tornado.gen.Return(data)

        while True:
            data = yield self.read(self._chunk_size)

            self._data_buffer.put(data)

            data = self._data_buffer.get_until_delim(delimiter)

            if data:
                raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_until_regex(self, pattern):
        '''Read until a regular expression from socket or buffer.

        Returns:
            bytes: The data including the match.
        '''
        data = self._data_buffer.get_until_regex(pattern)

        if data:
            raise tornado.gen.Return(data)

        while True:
            data = yield self.read(self._chunk_size)

            self._data_buffer.put(data)

            data = self._data_buffer.get_until_regex(pattern)

            if data:
                raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_until_close(self, streaming_callback=None):
        '''Read from the buffer and until the socket closes.

        Returns:
            bytes, None: Returns ``bytes`` if `streaming_callback` is not
            specified.
        '''

        if not streaming_callback:
            data_list = []

        while True:
            if self._data_buffer.has_data():
                data = self._data_buffer.get_bytes(self._chunk_size)
            else:
                try:
                    data = yield self.read(self._chunk_size)
                except StreamClosedError:
                    break

            if streaming_callback:
                streaming_callback(data)
            else:
                data_list.append(data)

        if streaming_callback:
            raise tornado.gen.Return(None)
        else:
            raise tornado.gen.Return(b''.join(data_list))

    def set_close_callback(self, callback):
        '''Set the callback that will invoked when the stream is closed.'''
        self._stream_closed_callback = tornado.stack_context.wrap(callback)

    def monitor_for_close(self):
        '''Wait for the stream to close.

        This function is used to keep the socket around until closed. Any
        data received is discarded. Any read or write functions will cause
        the wait to be cancelled.
        '''
        if self._state == State.connected:
            self._state = State.wait_for_close

            _logger.debug('Monitoring for close.')
            self._update_handler(READ | ERROR)

    def stop_monitor_for_close(self):
        '''Stop waiting for the socket to close.'''
        if self._state == State.wait_for_close:
            self._state = State.connected
            self._update_handler(0)

    def check_socket_closed(self):
        '''Check whether the socket was closed.

        Any data received is discarded. If any error occurs, the stream
        will be closed.
        '''
        _logger.debug('Check socket closed.')

        try:
            data = self._socket.recv(1)
        except ssl.SSLError as error:
            if error.errno != ssl.SSL_ERROR_WANT_READ:
                self.close()
        except IOError as error:
            if error.errno not in (errno.EWOULDBLOCK, errno.EINPROGRESS):
                self.close()
        else:
            if data:
                _logger.warning(
                    _('Server sent unwanted data after request finished.')
                )

            self.close()

        _logger.debug('Check socket closed={0}'.format(self.closed()))
        return self.closed()


class SSLIOStream(IOStream):
    '''Socket stream with SSL.

    Args:
        server_hostname (str): The server hostname.
        ssl_options (dict): Optional options for `ssl_wrap`.
    '''
    def __init__(self, *args, **kwargs):
        self._server_hostname = kwargs.pop('server_hostname')
        self._ssl_options = kwargs.pop('ssl_options', {})
        super().__init__(*args, **kwargs)

    @tornado.gen.coroutine
    def connect(self, address, timeout=None):
        yield super().connect(address, timeout=timeout)
        self._remove_handler()

        self._socket = tornado.netutil.ssl_wrap_socket(
            self._socket,
            self._ssl_options,
            server_hostname=self._server_hostname,
            do_handshake_on_connect=False
        )

        self._handle_socket()

        yield self._do_handshake(timeout)

        if self._ssl_options \
        and self._ssl_options.get('cert_reqs', None) != ssl.CERT_NONE:
            self._verify_certificates()

    @tornado.gen.coroutine
    def _do_handshake(self, timeout):
        '''Do the SSL handshake and return when finished.'''
        while True:
            try:
                self._socket.do_handshake()
            except ssl.SSLError as error:
                if error.errno == ssl.SSL_ERROR_WANT_READ:
                    events = yield self._wait_event(
                        READ | ERROR, timeout=timeout
                    )
                elif error.errno == ssl.SSL_ERROR_WANT_WRITE:
                    events = yield self._wait_event(
                        WRITE | ERROR, timeout=timeout
                    )
                else:
                    raise

                if events & ERROR:
                    self._raise_socket_error()

            except AttributeError as error:
                # May occur if connection reset. Issue #98.
                raise NetworkError('SSL socket not ready.') from error
            else:
                break

    def _verify_certificates(self):
        '''Verify the certificates.

        Raises:
            .errors.SSLVerficationError
        '''
        peer_certificate = self._socket.getpeercert()

        if not peer_certificate:
            raise SSLVerficationError('Server did not provide a certificate.')

        try:
            # XXX: Note the ssl_match_hostname function isn't documented in
            # the API docs.
            tornado.netutil.ssl_match_hostname(
                peer_certificate,
                self._server_hostname
            )
        except tornado.netutil.SSLCertificateError as error:
            raise SSLVerficationError('Invalid SSL certificate') from error


if __name__ == '__main__':
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    io_stream = SSLIOStream(sock, server_hostname='google.com', rw_timeout=5)

    @tornado.gen.coroutine
    def blah():
        yield io_stream.connect(('google.com', 443), 5)
        print('connected')
        yield io_stream.write(b'HEAD / HTTP/1.0\r\n\r\n')
        print('written!')
        data = yield io_stream.read(4096)
        print('got', data, len(data))
        io_stream.close()

    tornado.ioloop.IOLoop.current().run_sync(blah)
