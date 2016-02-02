# encoding=utf8

import socket
import ssl
import sys
import functools

import asyncio

from wpull.connection import Connection, ConnectionPool, HostPool, \
    HappyEyeballsTable
from wpull.dns import Resolver
from wpull.errors import NetworkError, NetworkTimedOut, SSLVerificationError
import wpull.testing.async
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


class TestConnectionPool(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_acquire(self):
        pool = ConnectionPool(max_host_count=2)

        conn1 = yield from pool.acquire('localhost', self.get_http_port())
        conn2 = yield from pool.acquire('localhost', self.get_http_port())

        yield from pool.release(conn1)
        yield from pool.release(conn2)

        conn3 = yield from pool.acquire('localhost', self.get_http_port())
        conn4 = yield from pool.acquire('localhost', self.get_http_port())

        yield from pool.release(conn3)
        yield from pool.release(conn4)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_session(self):
        pool = ConnectionPool()

        for dummy in range(10):
            session = yield from \
                pool.session('localhost', self.get_http_port())
            with session as connection:
                if connection.closed():
                    yield from connection.connect()

        self.assertEqual(1, len(pool.host_pools))
        host_pool = list(pool.host_pools.values())[0]
        self.assertIsInstance(host_pool, HostPool)
        self.assertEqual(1, host_pool.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_host_max_limit(self):
        pool = ConnectionPool(max_host_count=2)

        yield from pool.acquire('localhost', self.get_http_port())
        yield from pool.acquire('localhost', self.get_http_port())

        with self.assertRaises(asyncio.TimeoutError):
            yield from asyncio.wait_for(
                pool.acquire('localhost', self.get_http_port()),
                0.1
            )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_at_host_max_limit_cycling(self):
        pool = ConnectionPool(max_host_count=10, max_count=10)

        @asyncio.coroutine
        def con_fut():
            session = yield from pool.session('localhost', self.get_http_port())

            with session as connection:
                if connection.closed():
                    yield from connection.connect()

        futs = [con_fut() for dummy in range(10)]

        yield from asyncio.wait(futs)

        self.assertEqual(1, len(pool.host_pools))
        connection_pool_entry = list(pool.host_pools.values())[0]
        self.assertIsInstance(connection_pool_entry, HostPool)
        self.assertGreaterEqual(10, connection_pool_entry.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_over_host_max_limit_cycling(self):
        pool = ConnectionPool(max_host_count=10, max_count=10)

        @asyncio.coroutine
        def con_fut():
            session = yield from \
                pool.session('localhost', self.get_http_port())

            with session as connection:
                if connection.closed():
                    yield from connection.connect()

        futs = [con_fut() for dummy in range(20)]

        yield from asyncio.wait(futs)

        self.assertEqual(1, len(pool.host_pools))
        connection_pool_entry = list(pool.host_pools.values())[0]
        self.assertIsInstance(connection_pool_entry, HostPool)
        self.assertGreaterEqual(10, connection_pool_entry.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_multiple_hosts(self):
        pool = ConnectionPool(max_host_count=5, max_count=20)

        for port in range(10):
            session = yield from pool.session('localhost', port)

            with session as connection:
                self.assertTrue(connection)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_clean(self):
        pool = ConnectionPool(max_host_count=2)

        conn1 = yield from pool.acquire('localhost', self.get_http_port())
        conn2 = yield from pool.acquire('localhost', self.get_http_port())

        yield from pool.release(conn1)
        yield from pool.release(conn2)
        yield from pool.clean()

        self.assertEqual(0, len(pool.host_pools))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_release_clean_race_condition(self):
        pool = ConnectionPool(max_host_count=1)

        connection = yield from pool.acquire('127.0.0.1', 1234)
        connection_2_task = asyncio.async(pool.acquire('127.0.0.1', 1234))
        yield from asyncio.sleep(0.01)
        pool.no_wait_release(connection)
        yield from pool.clean(force=True)
        connection_2 = yield from connection_2_task

        # This line should not KeyError crash:
        yield from pool.release(connection_2)
