# encoding=utf8

import socket
import tornado.testing

from wpull.backport.testing import unittest
from wpull.iostream import DataBuffer, BufferFullError, IOStream
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestDataBuffer(unittest.TestCase):
    def test_get_bytes(self):
        buffer = DataBuffer()

        self.assertEqual(b'', buffer.get_bytes(6))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'12345', buffer.get_bytes(6))
        self.assertEqual(b'678', buffer.get_bytes(6))
        self.assertEqual(b'', buffer.get_bytes(6))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'1234', buffer.get_bytes(4))
        self.assertEqual(b'5', buffer.get_bytes(4))
        self.assertEqual(b'678', buffer.get_bytes(4))
        self.assertEqual(b'', buffer.get_bytes(4))

    def test_get_delim(self):
        buffer = DataBuffer()

        self.assertEqual(b'', buffer.get_until_delim(b'2'))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'12345', buffer.get_until_delim(b'5'))
        self.assertEqual(b'678', buffer.get_bytes(5))
        self.assertEqual(b'', buffer.get_bytes(5))
        self.assertEqual(b'', buffer.get_until_delim(b'2'))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'123456', buffer.get_until_delim(b'56'))
        self.assertEqual(b'78', buffer.get_bytes(5))

    def test_get_regex(self):
        buffer = DataBuffer()

        self.assertEqual(b'', buffer.get_until_regex(br'[23]'))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'12345', buffer.get_until_regex(br'[1-4]+5'))
        self.assertEqual(b'678', buffer.get_bytes(5))
        self.assertEqual(b'', buffer.get_bytes(5))
        self.assertEqual(b'', buffer.get_until_regex(b'2'))

        buffer.put(b'12345')
        buffer.put(b'678')

        self.assertEqual(b'123456', buffer.get_until_regex(br'3?56'))
        self.assertEqual(b'78', buffer.get_bytes(5))

    def test_buffer_full(self):
        buffer = DataBuffer(max_size=100)
        buffer.put(b'0' * 100)

        self.assertRaises(BufferFullError, buffer.put, b'1')


class TestIOStream(BadAppTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        socket_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        stream = IOStream(socket_obj)

        yield stream.connect(('127.0.0.1', self.get_http_port()))
        yield stream.write(b'GET / HTTP/1.0\r\n\r\n')

        headers = yield stream.read_until(b'\r\n\r\n')

        self.assertIn(b'OK', headers)

        body_1 = yield stream.read_until(b' ')
        body_2 = yield stream.read_until_close()

        self.assertEqual(b'hello world!', body_1 + body_2)

        self.assertTrue(stream.closed)
