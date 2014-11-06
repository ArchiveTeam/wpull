# encoding=utf-8
from trollius import From

from wpull.errors import ProtocolError
from wpull.http.request import Request
from wpull.http.web import WebClient, LoopType
import wpull.testing.async
from wpull.testing.badapp import BadAppTestCase
from wpull.testing.goodapp import GoodAppTestCase


DEFAULT_TIMEOUT = 30


class TestWebClient(GoodAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/')))

        self.assertFalse(session.done())
        response = yield From(session.fetch())

        self.assertEqual(200, response.status_code)
        self.assertTrue(session.done())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/redirect')))

        status_codes = []

        while not session.done():
            response = yield From(session.fetch())
            if not status_codes:
                self.assertEqual(LoopType.redirect, session.loop_type())
            status_codes.append(response.status_code)

        self.assertEqual([301, 200], status_codes)
        self.assertTrue(session.done())
        self.assertEqual(LoopType.normal, session.loop_type())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_repeat(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/redirect?code=307')))

        status_codes = []

        while not session.done():
            response = yield From(session.fetch())
            if not status_codes:
                self.assertEqual(LoopType.redirect, session.loop_type())
            status_codes.append(response.status_code)

        self.assertEqual([307, 200], status_codes)
        self.assertTrue(session.done())
        self.assertEqual(LoopType.normal, session.loop_type())


class TestWebClientBadCase(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_redirect(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/bad_redirect')))

        while not session.done():
            try:
                yield From(session.fetch())
            except ProtocolError:
                return
            else:
                self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_redirect_ipv6(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/bad_redirect_ipv6')))

        while not session.done():
            try:
                yield From(session.fetch())
            except ProtocolError:
                return
            else:
                self.fail()  # pragma: no cover

