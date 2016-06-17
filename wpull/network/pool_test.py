import asyncio

import functools

import wpull.testing.async
from wpull.network.connection import Connection
from wpull.network.dns import Resolver, IPFamilyPreference
from wpull.network.pool import ConnectionPool, HostPool, HappyEyeballsTable
from wpull.testing.badapp import BadAppTestCase


class TestConnectionPool(BadAppTestCase):
    @wpull.testing.async.async_test()
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

    @wpull.testing.async.async_test()
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

    @wpull.testing.async.async_test()
    def test_host_max_limit(self):
        pool = ConnectionPool(max_host_count=2)

        yield from pool.acquire('localhost', self.get_http_port())
        yield from pool.acquire('localhost', self.get_http_port())

        with self.assertRaises(asyncio.TimeoutError):
            yield from asyncio.wait_for(
                pool.acquire('localhost', self.get_http_port()),
                0.1
            )

    @wpull.testing.async.async_test()
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

    @wpull.testing.async.async_test()
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

    @wpull.testing.async.async_test()
    def test_multiple_hosts(self):
        pool = ConnectionPool(max_host_count=5, max_count=20)

        for port in range(10):
            session = yield from pool.session('localhost', port)

            with session as connection:
                self.assertTrue(connection)

    @wpull.testing.async.async_test()
    def test_clean(self):
        pool = ConnectionPool(max_host_count=2)

        conn1 = yield from pool.acquire('localhost', self.get_http_port())
        conn2 = yield from pool.acquire('localhost', self.get_http_port())

        yield from pool.release(conn1)
        yield from pool.release(conn2)
        yield from pool.clean()

        self.assertEqual(0, len(pool.host_pools))

    @wpull.testing.async.async_test()
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

    @wpull.testing.async.async_test()
    def test_happy_eyeballs(self):
        connection_factory = functools.partial(Connection, connect_timeout=10)
        resolver = Resolver()
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
