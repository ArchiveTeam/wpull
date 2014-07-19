# encoding=utf-8
import functools
import io

from trollius import From

from wpull.connection import ConnectionPool, Connection
from wpull.errors import NetworkError
from wpull.http.client import Client
from wpull.http.request import Request
import wpull.testing.async
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestClient(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        client = Client()

        with client.session() as session:
            request = Request(self.get_url('/'))
            response = yield From(session.fetch(request))

            self.assertEqual(200, response.status_code)
            self.assertEqual(request, response.request)

            file_obj = io.BytesIO()
            yield From(session.read_content(file_obj))

            self.assertEqual(b'hello world!', file_obj.getvalue())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_throw(self):
        client = Client()

        with client.session() as session:
            request = Request('http://wpull-no-exist.invalid')

        try:
            yield From(session.fetch(request))
        except NetworkError:
            pass
        else:
            self.fail()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_recovery(self):
        connection_factory = functools.partial(Connection, timeout=2.0)
        connection_pool = ConnectionPool(connection_factory=connection_factory)
        client = Client(connection_pool)

        for dummy in range(7):
            with client.session() as session:
                request = Request(self.get_url('/header_early_close'))
                try:
                    yield From(session.fetch(request))
                except NetworkError:
                    pass
                else:
                    self.fail()

        for dummy in range(7):
            with client.session() as session:
                request = Request(self.get_url('/'))
                response = yield From(session.fetch(request))
                self.assertEqual(200, response.status_code)
                yield From(session.read_content())
