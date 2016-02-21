# encoding=utf-8
import io

from wpull.protocol.abstract.client import DurationTimeout

from wpull.errors import ProtocolError
from wpull.protocol.http.request import Request
from wpull.protocol.http.web import WebClient, LoopType
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
        response = yield from session.start()

        body = io.BytesIO()
        yield from session.download(body)

        self.assertEqual(200, response.status_code)
        self.assertTrue(session.done())
        self.assertIn(b'Example Site', body.getvalue())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/redirect')))

        status_codes = []

        while not session.done():
            response = yield from session.start()
            if not status_codes:
                self.assertEqual(LoopType.redirect, session.loop_type())
            status_codes.append(response.status_code)
            yield from session.download()

        self.assertEqual([301, 200], status_codes)
        self.assertTrue(session.done())
        self.assertEqual(LoopType.normal, session.loop_type())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_repeat(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/redirect?code=307')))

        status_codes = []

        while not session.done():
            response = yield from session.start()
            if not status_codes:
                self.assertEqual(LoopType.redirect, session.loop_type())
            status_codes.append(response.status_code)
            yield from session.download()

        self.assertEqual([307, 200], status_codes)
        self.assertTrue(session.done())
        self.assertEqual(LoopType.normal, session.loop_type())


class TestWebClientBadCase(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_redirect(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/bad_redirect')))

        with self.assertRaises(ProtocolError):
            while not session.done():
                yield from session.start()
                yield from session.download()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_redirect_ipv6(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/bad_redirect_ipv6')))

        with self.assertRaises(ProtocolError):
            while not session.done():
                yield from session.start()
                yield from session.download()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_duration_timeout(self):
        client = WebClient()
        session = client.session(Request(self.get_url('/sleep_long')))

        with self.assertRaises(DurationTimeout):
            yield from session.start()
            yield from session.download(duration_timeout=0.1)
