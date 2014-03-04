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
import tornado.gen
import tornado.ioloop
import toro

from wpull.errors import NetworkError
from wpull.extended import StreamQueue


_logger = logging.getLogger('__name__')
ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)
ERRNO_CONNRESET = (errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE)


class State(object):
    startup = 1
    connecting = 2
    connected = 3
    closed = 4


class BaseIOStream(object, metaclass=abc.ABCMeta):
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
        pass

    @abc.abstractmethod
    def _close_fd(self):
        pass

    @abc.abstractmethod
    def _write_to_fd(self, data):
        pass

    @abc.abstractmethod
    def _read_from_fd(self):
        pass

    def get_fd_error(self):
        return None

    @tornado.gen.coroutine
    def read_until_regex(self, regex):
        chunk_buffer = collections.deque()

        while True:
            data = yield self.read_bytes(4096)
            match = re.search(regex, data)

            if match:
                chunk_buffer.append(data[:match.end()])
                self._local_read_queue.appendleft(data[match.end():])
                raise tornado.gen.Return(b''.join(chunk_buffer))

            chunk_buffer.append(data)
            double_prefix(chunk_buffer)

    @tornado.gen.coroutine
    def read_until(self, delimiter):
        chunk_buffer = collections.deque()

        while True:
            data = yield self.read_bytes(4096)
            loc = data.find(delimiter)

            if loc != -1:
                chunk_buffer.append(data[:loc + 1])
                self._local_read_queue.appendleft(data[loc + 1:])
                raise tornado.gen.Return(b''.join(chunk_buffer))

            chunk_buffer.append(data)
            double_prefix(chunk_buffer)

    @tornado.gen.coroutine
    def read_bytes(self, num_bytes, streaming_callback=None):
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
        raise tornado.gen.Return(
            (yield self.read_bytes(None, streaming_callback))
        )

    def read_bytes_queue(self, num_bytes):
        return self._read_with_queue(self.read_bytes, num_bytes)

    def read_until_close_queue(self):
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
        yield self._write_queue.put(data, deadline=self._write_timeout)

    def close(self):
        if not self.closed:
            _logger.debug('Closing stream.')
            self._io_loop.remove_handler(self.fileno())
            self._close_fd()
            self._read_queue.put(None)

        self._state = State.closed

    def _start(self):
        _logger.debug('Starting handler and loops.')
        self._io_loop.add_handler(
            self.fileno(), self._event_handler,
            self._io_loop.READ | self._io_loop.WRITE | self._io_loop.ERROR
        )
        self._io_loop.add_future(self._read_loop(), self._loop_end_handler)
        self._io_loop.add_future(self._write_loop(), self._loop_end_handler)

    def _event_handler(self, fd, events):
        if events & tornado.ioloop.IOLoop.READ:
            self._read_event.notify()

        if events & tornado.ioloop.IOLoop.WRITE:
            self._write_event.notify()

        if events & tornado.ioloop.IOLoop.ERROR:
            self.close()

    def _loop_end_handler(self, future):
        try:
            future.result()
        except Exception:
            _logger.exception('Loop ended.')
            self.close()

    @tornado.gen.coroutine
    def _read_loop(self):
        while not self.closed:
            yield self._read_event.wait()
            data = self._read_from_fd()
            yield self._read_queue.put(data)

    @tornado.gen.coroutine
    def _write_loop(self):
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
    def connect(self, address):
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
