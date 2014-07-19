# encoding=utf8

from trollius import From
import trollius

from wpull.connection import Connection, ConnectionPool, HostPool
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
    def test_connection_pool_basic(self):
        pool = ConnectionPool(max_host_count=2)

        yield From(pool.check_out('localhost', self.get_http_port()))
        yield From(pool.check_out('localhost', self.get_http_port()))

        try:
            yield From(trollius.wait_for(
                pool.check_out('localhost', self.get_http_port()),
                0
            ))
        except trollius.TimeoutError:
            pass
        else:
            self.fail()

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
        connection_pool = ConnectionPool()

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
