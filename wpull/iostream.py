# encoding=utf-8
'''Socket streams.'''
import datetime
import errno
import os
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
    not_yet_connected = 1
    connecting = 2
    connected = 3
    closed = 4


class IOStream(object):
    def __init__(self, socket_obj, ioloop=None):
        self._socket = socket_obj
        self._state = State.not_yet_connected
        self._ioloop = ioloop or tornado.ioloop.IOLoop.current()
        self._event_result = None

        self._ioloop.add_handler(socket_obj.fileno(), self._event_handler, 0)

    @property
    def socket(self):
        return self._socket

    @property
    def closed(self):
        return self._state == State.closed

    def _event_handler(self, fd, events):
        self._event_result.set(events)
        self._update_handler(0)

    @tornado.gen.coroutine
    def _wait_event(self, events, timeout=None):
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
        self._ioloop.update_handler(self._socket.fileno(), events)

    def _raise_socket_error(self):
        error_code = self._socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_ERROR
            )

        self.close()
        raise NetworkError(error_code, os.strerror(error_code))

    def close(self):
        self._state = State.closed
        self._socket.close()
        self._ioloop.remove_handler(self._socket.fileno())

    @tornado.gen.coroutine
    def connect(self, address, timeout=None):
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
        events = yield self._wait_event(WRITE | ERROR, timeout=timeout)

        if events & ERROR:
            self._raise_socket_error()

        self._socket.send(data)

    @tornado.gen.coroutine
    def read(self, length, timeout=None):
        events = yield self._wait_event(READ | ERROR, timeout=timeout)

        if events & ERROR:
            self._raise_socket_error()

        data = self._socket.recv(length)

        raise tornado.gen.Return(data)


if __name__ == '__main__':
    socket_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    io_stream = IOStream(socket_obj)

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
