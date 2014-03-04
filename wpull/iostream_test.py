# encoding=utf-8

import socket
import tornado

from wpull.iostream import IOStream
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestIOStream(BadAppTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_iostream_until_close(self):
        socket_instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        io_stream = IOStream(socket_instance)

        yield io_stream.connect(('localhost', self.get_http_port()))
        yield io_stream.write(b'GET / HTTP/1.0\r\n\r\n')

        data = yield io_stream.read_until_close()

        self.assertIn(b'hello world!', data)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_iostream_read_bytes(self):
        socket_instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        io_stream = IOStream(socket_instance)

        yield io_stream.connect(('localhost', self.get_http_port()))
        yield io_stream.write(b'GET / HTTP/1.0\r\n\r\n')

        data = yield io_stream.read_bytes(4)

        self.assertEqual(b'HTTP', data)

        io_stream.close()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_iostream_delim(self):
        socket_instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        io_stream = IOStream(socket_instance)

        yield io_stream.connect(('localhost', self.get_http_port()))
        yield io_stream.write(b'GET / HTTP/1.0\r\n\r\n')

        data = yield io_stream.read_until(b'\n')

        self.assertEqual(b'HTTP/1.1 200 OK\r\n', data)

        io_stream.close()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_iostream_regex(self):
        socket_instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        io_stream = IOStream(socket_instance)

        yield io_stream.connect(('localhost', self.get_http_port()))
        yield io_stream.write(b'GET / HTTP/1.0\r\n\r\n')

        data = yield io_stream.read_until_regex(br'\n')

        self.assertEqual(b'HTTP/1.1 200 OK\r\n', data)

        io_stream.close()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_big(self):
        socket_instance = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        io_stream = IOStream(socket_instance)

        yield io_stream.connect(('localhost', self.get_http_port()))
        yield io_stream.write(b'GET /big HTTP/1.0\r\n\r\n')

        stream_queue = io_stream.read_until_close_queue()
        length = 0

        while True:
            data = yield stream_queue.get()

            if data is None:
                break

            length += len(data)

        self.assertGreater(length, 50000000)
        io_stream.close()
