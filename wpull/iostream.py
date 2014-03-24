# encoding=utf-8
'''Socket streams.'''
import collections
import datetime
import errno
import os
import re
import socket
import tornado.gen
import tornado.ioloop
import toro

from wpull.errors import NetworkError
from wpull.util import TimedOut


WRITE = tornado.ioloop.IOLoop.WRITE
READ = tornado.ioloop.IOLoop.READ
ERROR = tornado.ioloop.IOLoop.ERROR


class State(object):
    '''Connection states.'''
    not_yet_connected = 1
    '''Not yet connected.'''
    connecting = 2
    '''Connecting.'''
    connected = 3
    '''Connected.'''
    closed = 4
    '''Closed.'''


class BufferFullError(ValueError):
    '''Exception for Data Buffer when the buffer is full.'''


class StreamClosed(IOError):
    '''Stream is closed.'''


class DataBuffer(object):
    '''A growing data buffer.

    This buffer uses algorithms similar to :class:`tornado.iostream`.
    '''
    def __init__(self, max_size=1048576):
        self._data = collections.deque()
        self._num_bytes = 0
        self._max_size = max_size

    @property
    def num_bytes(self):
        '''Return the number of bytes in the buffer.'''
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
        '''Return the data up to and including the delimiter.'''
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
        '''Return the data up to and including the match.'''
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
        '''Put data into the buffer.'''
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
        socket_obj: A socket object.
        ioloop: IOLoop.
        chunk_size (int): The number of bytes read per receive call.
    '''
    def __init__(self, socket_obj, ioloop=None, chunk_size=4096):
        self._socket = socket_obj
        self._state = State.not_yet_connected
        self._ioloop = ioloop or tornado.ioloop.IOLoop.current()
        self._event_result = None
        self._chunk_size = chunk_size
        self._data_buffer = DataBuffer()

        self._ioloop.add_handler(socket_obj.fileno(), self._event_handler, 0)

    @property
    def socket(self):
        '''Return the socket.'''
        return self._socket

    @property
    def state(self):
        '''Return the current state.'''
        return self._state

    @property
    def closed(self):
        '''Return whether the stream is closed.'''
        return self._state == State.closed

    def _event_handler(self, fd, events):
        '''Handle and set the async result and clear the event listener.'''
        self._event_result.set(events)
        self._update_handler(0)

    @tornado.gen.coroutine
    def _wait_event(self, events, timeout=None):
        '''Set the events to listen for and wait for it to occur.'''
        deadline = datetime.timedelta(seconds=timeout) if timeout else None
        self._event_result = toro.AsyncResult()

        self._update_handler(events)

        try:
            events = yield self._event_result.get(deadline)
        except toro.Timeout as error:
            raise TimedOut('Timed out.') from error

        self._update_handler(0)

        raise tornado.gen.Return(events)

    def _update_handler(self, events):
        '''Update the IOLoop events to listen for.'''
        self._ioloop.update_handler(self._socket.fileno(), events)

    def _raise_socket_error(self):
        '''Get the error from the socket and raise an error.'''
        error_code = self._socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_ERROR
            )

        self.close()
        raise NetworkError(error_code, os.strerror(error_code))

    def close(self):
        '''Close the socket.'''
        self._state = State.closed
        self._socket.close()
        self._ioloop.remove_handler(self._socket.fileno())

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
        self._state = State.connected

        try:
            self._socket.connect(address)
        except BlockingIOError as error:
            code = error.args[0]

            if code not in (errno.EWOULDBLOCK, errno.EINPROGRESS):
                raise

        try:
            events = yield self._wait_event(
                READ | WRITE | ERROR, timeout=timeout
            )
        except TimedOut as error:
            self.close()
            raise TimedOut('Socket connect timed out.') from error

        if events & ERROR:
            self._raise_socket_error()

    @tornado.gen.coroutine
    def write(self, data, timeout=None):
        '''Write to socket.'''
        events = yield self._wait_event(WRITE | ERROR, timeout=timeout)

        if events & ERROR:
            self._raise_socket_error()

        self._socket.send(data)

    @tornado.gen.coroutine
    def read(self, length, timeout=None):
        '''Read from socket.'''
        if self._data_buffer.has_data():
            raise tornado.gen.Return(self._data_buffer.get_bytes(length))

        events = yield self._wait_event(READ | ERROR, timeout=timeout)

        if events & ERROR:
            self._raise_socket_error()

        data = self._socket.recv(length)

        if not data:
            self.close()
            raise StreamClosed('Stream is closed.')

        raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_bytes(self, length, streaming_callback=None, timeout=None):
        '''Read exactly `length` bytes from the socket.

        Args:
            length (int): Number of bytes to read.
            streaming_callback: A callback function that receives data.
            timeout (float): A timeout in seconds.

        Returns:
            bytes,None
        '''
        bytes_left = length

        if not streaming_callback:
            data_list = []

        while bytes_left > 0:
            data = yield self.read(self._chunk_size, timeout=timeout)
            bytes_left -= len(data)

            if streaming_callback:
                streaming_callback(data)
            else:
                data_list.append(data)

        if streaming_callback:
            raise tornado.gen.Return(None)
        else:
            raise tornado.gen.Return(b''.join(data_list))

    @tornado.gen.coroutine
    def read_until(self, delimiter, timeout=None):
        '''Read until a delimiter.

        Returns:
            bytes: The data including the delimiter.
        '''
        data = self._data_buffer.get_until_delim(delimiter)

        if data:
            raise tornado.gen.Return(data)

        while True:
            data = yield self.read(self._chunk_size, timeout=timeout)

            self._data_buffer.put(data)

            data = self._data_buffer.get_until_delim(delimiter)

            if data:
                raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_until_regex(self, pattern, timeout=None):
        '''Read until a regular expression.

        Returns:
            bytes: The data including the match.
        '''
        data = self._data_buffer.get_until_regex(pattern)

        if data:
            raise tornado.gen.Return(data)

        while True:
            data = yield self.read(self._chunk_size, timeout=timeout)

            self._data_buffer.put(data)

            data = self._data_buffer.get_until_regex(pattern)

            if data:
                raise tornado.gen.Return(data)

    @tornado.gen.coroutine
    def read_until_close(self, streaming_callback=None, timeout=None):
        '''Read until the socket closes.

        Returns:
            bytes,None
        '''

        if not streaming_callback:
            data_list = []

        while True:
            try:
                data = yield self.read(self._chunk_size, timeout=timeout)
            except StreamClosed:
                break

            if streaming_callback:
                streaming_callback(data)
            else:
                data_list.append(data)

        if streaming_callback:
            raise tornado.gen.Return(None)
        else:
            raise tornado.gen.Return(b''.join(data_list))


if __name__ == '__main__':
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    io_stream = IOStream(sock)

    @tornado.gen.coroutine
    def blah():
        yield io_stream.connect(('google.com', 80), 5)
        print('connected')
        yield io_stream.write(b'HEAD / HTTP/1.0\r\n\r\n', 5)
        print('written!')
        data = yield io_stream.read(4096, 5)
        print('got', data, len(data))
        io_stream.close()

    tornado.ioloop.IOLoop.current().run_sync(blah)
