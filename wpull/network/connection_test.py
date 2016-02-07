# encoding=utf8

import asyncio
import functools
import socket
import ssl
import sys

import wpull.testing.async
from wpull.errors import NetworkError, NetworkTimedOut, SSLVerificationError
from wpull.network.connection import Connection, ConnectionPool, HostPool, \
    HappyEyeballsTable
from wpull.network.dns import Resolver
from wpull.testing.badapp import BadAppTestCase, SSLBadAppTestCase

DEFAULT_TIMEOUT = 30


class TestConnection(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')
        yield from connection.connect()
        yield from connection.write(b'GET / HTTP/1.0\r\n\r\n')
        data = yield from connection.read()

        self.assertEqual(b'hello world!', data[-12:])

        self.assertTrue(connection.closed())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_connect_socket_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            raise socket.error(123, 'Mock error')

        with self.assertRaises(NetworkError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_connect_ssl_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            raise ssl.SSLError(123, 'Mock error')

        with self.assertRaises(NetworkError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_socket_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            if sys.version_info < (3, 3):
                raise socket.error(123, 'Mock error')
            else:
                raise ConnectionError(123, 'Mock error')

        with self.assertRaises(NetworkError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_ssl_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            if sys.version_info < (3, 3):
                raise socket.error(123, 'Mock error')
            else:
                raise ConnectionError(123, 'Mock error')

        with self.assertRaises(NetworkError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_certificate_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            raise ssl.SSLError(1, 'I has a Certificate Error!')

        with self.assertRaises(SSLVerificationError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_unknown_ca_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @asyncio.coroutine
        def mock_func():
            raise ssl.SSLError(1, 'Uh oh! Unknown CA!')

        with self.assertRaises(SSLVerificationError):
            yield from connection.run_network_operation(mock_func())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connect_timeout(self):
        connection = Connection(('10.0.0.0', 1), connect_timeout=2)

        with self.assertRaises(NetworkTimedOut):
            yield from connection.connect()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_read_timeout(self):
        connection = Connection(('127.0.0.1', self.get_http_port()),
                                timeout=0.5)
        yield from connection.connect()
        yield from connection.write(b'GET /sleep_long HTTP/1.1\r\n',
                                    drain=False)
        yield from connection.write(b'\r\n', drain=False)

        data = yield from connection.readline()
        self.assertEqual(b'HTTP', data[:4])

        while True:
            data = yield from connection.readline()

            if not data.strip():
                break

        with self.assertRaises(NetworkTimedOut):
            bytes_left = 2
            while bytes_left > 0:
                data = yield from connection.read(bytes_left)

                if not data:
                    break

                bytes_left -= len(data)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_sock_reuse(self):
        connection1 = Connection(('127.0.0.1', self.get_http_port()))
        yield from connection1.connect()

        connection2 = Connection(
            ('127.0.0.1', self.get_http_port()),
            sock=connection1.writer.get_extra_info('socket')
        )

        yield from connection2.connect()
        yield from connection2.write(b'GET / HTTP/1.1\r\n\r\n')

        data = yield from connection2.readline()
        self.assertEqual(b'HTTP', data[:4])

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_happy_eyeballs_prefer_ipv4(self):
        connection_factory = functools.partial(Connection, connect_timeout=10)
        resolver = Resolver(family=Resolver.PREFER_IPv4)
        pool = ConnectionPool(resolver=resolver,
                              connection_factory=connection_factory)

        conn1 = yield from pool.acquire('google.com', 80)
        conn2 = yield from pool.acquire('google.com', 80)

        yield from conn1.connect()
        yield from conn2.connect()
        conn1.close()
        conn2.close()

        yield from pool.release(conn1)
        yield from pool.release(conn2)

        conn3 = yield from pool.acquire('google.com', 80)

        yield from conn3.connect()
        conn3.close()

        yield from pool.release(conn3)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_happy_eyeballs_prefer_ipv6(self):
        connection_factory = functools.partial(Connection, connect_timeout=10)
        resolver = Resolver(family=Resolver.PREFER_IPv6)
        pool = ConnectionPool(resolver=resolver,
                              connection_factory=connection_factory)

        conn1 = yield from pool.acquire('google.com', 80)
        conn2 = yield from pool.acquire('google.com', 80)

        yield from conn1.connect()
        yield from conn2.connect()
        conn1.close()
        conn2.close()

        yield from pool.release(conn1)
        yield from pool.release(conn2)

        conn3 = yield from pool.acquire('google.com', 80)

        yield from conn3.connect()
        conn3.close()

        yield from pool.release(conn3)

    def test_happy_eyeballs_table(self):
        table = HappyEyeballsTable()

        self.assertIsNone(table.get_preferred('127.0.0.1', '::1'))

        table.set_preferred('::1', '127.0.0.1', '::1')

        self.assertEqual('::1', table.get_preferred('127.0.0.1', '::1'))
        self.assertEqual('::1', table.get_preferred('::1', '127.0.0.1'))

        table.set_preferred('::1', '::1', '127.0.0.1')

        self.assertEqual('::1', table.get_preferred('127.0.0.1', '::1'))
        self.assertEqual('::1', table.get_preferred('::1', '127.0.0.1'))

        table.set_preferred('127.0.0.1', '::1', '127.0.0.1')

        self.assertEqual('127.0.0.1', table.get_preferred('127.0.0.1', '::1'))
        self.assertEqual('127.0.0.1', table.get_preferred('::1', '127.0.0.1'))


class TestConnectionSSL(SSLBadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_start_tls(self):
        connection = Connection(('127.0.0.1', self.get_http_port()), timeout=1)

        yield from connection.connect()

        ssl_connection = yield from connection.start_tls()

        yield from ssl_connection.write(b'GET / HTTP/1.1\r\n\r\n')

        data = yield from ssl_connection.readline()
        self.assertEqual(b'HTTP', data[:4])



