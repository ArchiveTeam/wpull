# encoding=utf8

from trollius import From
import trollius

from wpull.connection import Connection, ConnectionPool
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
    def test_connection_pool(self):
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
