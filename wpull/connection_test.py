# encoding=utf8

import socket
import ssl
import sys

from trollius import From
import trollius

from wpull.connection import Connection, ConnectionPool, HostPool
from wpull.errors import NetworkError, NetworkTimedOut, SSLVerificationError
import wpull.testing.async
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestConnection(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')
        yield From(connection.connect())
        yield From(connection.write(b'GET / HTTP/1.0\r\n\r\n'))
        data = yield From(connection.read())

        self.assertEqual(b'hello world!', data[-12:])

        self.assertTrue(connection.closed())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_connect_socket_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            raise socket.error(123, 'Mock error')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_connect_ssl_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            raise ssl.SSLError(123, 'Mock error')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_socket_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            if sys.version_info < (3, 3):
                raise socket.error(123, 'Mock error')
            else:
                raise ConnectionError(123, 'Mock error')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_ssl_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            if sys.version_info < (3, 3):
                raise socket.error(123, 'Mock error')
            else:
                raise ConnectionError(123, 'Mock error')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_certificate_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            raise ssl.SSLError(1, 'I has a Certificate Error!')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except SSLVerificationError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_mock_request_unknown_ca_error(self):
        connection = Connection(
            ('127.0.0.1', self.get_http_port()), 'localhost')

        @trollius.coroutine
        def mock_func():
            raise ssl.SSLError(1, 'Uh oh! Unknown CA!')

        try:
            yield From(connection.run_network_operation(mock_func()))
        except SSLVerificationError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_basic(self):
        pool = ConnectionPool(max_host_count=2)

        yield From(pool.check_out('localhost', self.get_http_port()))
        yield From(pool.check_out('localhost', self.get_http_port()))

        try:
            yield From(trollius.wait_for(
                pool.check_out('localhost', self.get_http_port()),
                0.1
            ))
        except trollius.TimeoutError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_min(self):
        connection_pool = ConnectionPool()

        for dummy in range(2):
            session = yield From(
                connection_pool.session('localhost', self.get_http_port()))
            with session as connection:
                if connection.closed():
                    yield From(connection.connect())

        self.assertEqual(1, len(connection_pool.pool))
        connection_pool_entry = list(connection_pool.pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostPool)
        self.assertEqual(1, connection_pool_entry.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_max(self):
        connection_pool = ConnectionPool()

        @trollius.coroutine
        def con_fut():
            session = yield From(
                connection_pool.session('localhost', self.get_http_port()))
            with session as connection:
                if connection.closed():
                    yield From(connection.connect())

        futs = [con_fut() for dummy in range(6)]

        yield From(trollius.wait(futs))

        self.assertEqual(1, len(connection_pool.pool))
        connection_pool_entry = list(connection_pool.pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostPool)
        self.assertEqual(6, connection_pool_entry.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_over_max(self):
        connection_pool = ConnectionPool()

        @trollius.coroutine
        def con_fut():
            session = yield From(
                connection_pool.session('localhost', self.get_http_port()))
            with session as connection:
                if connection.closed():
                    yield From(connection.connect())

        futs = [con_fut() for dummy in range(12)]

        yield From(trollius.wait(futs))

        self.assertEqual(1, len(connection_pool.pool))
        connection_pool_entry = list(connection_pool.pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostPool)
        self.assertEqual(6, connection_pool_entry.count())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_clean(self):
        connection_pool = ConnectionPool(max_count=3)

        @trollius.coroutine
        def con_fut():
            session = yield From(
                connection_pool.session('localhost', self.get_http_port()))
            with session as connection:
                if connection.closed():
                    yield From(connection.connect())
                connection.close()

        futs = [con_fut() for dummy in range(12)]

        yield From(trollius.wait(futs))
        connection_pool.clean()

        self.assertEqual(0, len(connection_pool.pool))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connect_timeout(self):
        connection = Connection(('10.0.0.0', 1), connect_timeout=2)

        try:
            yield From(connection.connect())
        except NetworkTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_read_timeout(self):
        connection = Connection(('127.0.0.1', self.get_http_port()),
                                timeout=0.5)
        yield From(connection.connect())
        yield From(connection.write(b'GET /sleep_long HTTP/1.1\r\n',
                                    drain=False))
        yield From(connection.write(b'\r\n', drain=False))

        data = yield From(connection.readline())
        self.assertEqual(b'HTTP', data[:4])

        while True:
            data = yield From(connection.readline())

            if not data.strip():
                break

        try:
            bytes_left = 2
            while bytes_left > 0:
                data = yield From(connection.read(bytes_left))

                if not data:
                    break

                bytes_left -= len(data)
        except NetworkTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_check_in_clean_race_condition(self):
        connection_pool = ConnectionPool(max_host_count=1)

        connection = yield From(connection_pool.check_out('127.0.0.1', 1234))
        connection_2_task = trollius.async(connection_pool.check_out('127.0.0.1', 1234))
        yield From(trollius.sleep(0.01))
        connection_pool.check_in(connection)
        connection_pool.clean(force=True)
        connection_2 = yield From(connection_2_task)

        # This line should not KeyError crash:
        connection_pool.check_in(connection_2)
