# encoding=utf-8
import functools
import io
import warnings

import wpull.testing.async
from wpull.errors import NetworkError
from wpull.network.connection import Connection
from wpull.network.pool import ConnectionPool
from wpull.protocol.abstract.client import DurationTimeout
from wpull.protocol.http.client import Client
from wpull.protocol.http.request import Request
from wpull.testing.badapp import BadAppTestCase


class MyException(ValueError):
    pass


class TestClient(BadAppTestCase):
    @wpull.testing.async.async_test()
    def test_basic(self):
        client = Client()

        with client.session() as session:
            request = Request(self.get_url('/'))
            response = yield from session.start(request)

            self.assertEqual(200, response.status_code)
            self.assertEqual(request, response.request)

            file_obj = io.BytesIO()
            yield from session.download(file_obj)

            self.assertEqual(b'hello world!', file_obj.getvalue())

            self.assertTrue(request.url_info)
            self.assertTrue(request.address)
            self.assertTrue(response.body)

    @wpull.testing.async.async_test()
    def test_client_exception_throw(self):
        client = Client()

        with client.session() as session:
            request = Request('http://wpull-no-exist.invalid')

        with self.assertRaises(NetworkError):
            yield from session.start(request)

    @wpull.testing.async.async_test()
    def test_client_duration_timeout(self):
        client = Client()

        with self.assertRaises(DurationTimeout), client.session() as session:
            request = Request(self.get_url('/sleep_long'))
            yield from session.start(request)
            yield from session.download(duration_timeout=0.1)

    @wpull.testing.async.async_test()
    def test_client_exception_recovery(self):
        connection_factory = functools.partial(Connection, timeout=2.0)
        connection_pool = ConnectionPool(connection_factory=connection_factory)
        client = Client(connection_pool=connection_pool)

        for dummy in range(7):
            with self.assertRaises(NetworkError), client.session() as session:
                request = Request(self.get_url('/header_early_close'))
                yield from session.start(request)

        for dummy in range(7):
            with client.session() as session:
                request = Request(self.get_url('/'))
                response = yield from session.start(request)
                self.assertEqual(200, response.status_code)
                yield from session.download()
                self.assertTrue(session.done())

    @wpull.testing.async.async_test()
    def test_client_did_not_complete(self):
        client = Client()

        with warnings.catch_warnings(record=True) as warn_list:
            warnings.simplefilter("always")

            with client.session() as session:
                request = Request(self.get_url('/'))
                yield from session.start(request)
                self.assertFalse(session.done())

            for warn_obj in warn_list:
                print(warn_obj)

            # Unrelated warnings may occur in PyPy
            # https://travis-ci.org/chfoo/wpull/jobs/51420202
            self.assertGreaterEqual(len(warn_list), 1)

            for warn_obj in warn_list:
                if str(warn_obj.message) == 'HTTP session did not complete.':
                    break
            else:
                self.fail('Warning did not occur.')

        client = Client()

        with self.assertRaises(MyException):
            with client.session() as session:
                request = Request(self.get_url('/'))
                yield from session.start(request)
                raise MyException('Oops')
