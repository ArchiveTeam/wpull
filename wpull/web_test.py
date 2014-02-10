# encoding=utf-8
import tornado.testing

from wpull.backport.testing import unittest
from wpull.http import Response, Client, Request
from wpull.testing.goodapp import GoodAppTestCase
from wpull.web import RedirectTracker, RichClient, RichClientResponseType


class TestWeb(unittest.TestCase):
    def test_redirect_tracker(self):
        tracker = RedirectTracker(5)

        self.assertFalse(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertFalse(tracker.next_location(raw=True))
        self.assertEqual(0, tracker.count())

        response = Response('HTTP/1.1', 200, '')

        tracker.load(response)

        self.assertFalse(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertFalse(tracker.next_location())
        self.assertEqual(0, tracker.count())

        response = Response('HTTP/1.1', 303, '')
        response.fields['location'] = '/test'

        tracker.load(response)

        self.assertTrue(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertEqual('/test', tracker.next_location(raw=True))
        self.assertEqual(1, tracker.count())

        response = Response('HTTP/1.1', 307, '')
        response.fields['location'] = '/test'

        tracker.load(response)
        tracker.load(response)
        tracker.load(response)
        tracker.load(response)
        tracker.load(response)

        self.assertTrue(tracker.is_redirect())
        self.assertTrue(tracker.is_repeat())
        self.assertTrue(tracker.exceeded())
        self.assertEqual('/test', tracker.next_location(raw=True))
        self.assertEqual(6, tracker.count())


class TestRichClient(GoodAppTestCase):
    @tornado.testing.gen_test
    def test_basic(self):
        http_client = Client()
        client = RichClient(http_client)
        session = client.session(Request.new(self.get_url('/')))

        self.assertFalse(session.done)
        response = yield session.fetch()

        self.assertEqual(200, response.status_code)
        self.assertTrue(session.done)

    @tornado.testing.gen_test
    def test_redirect(self):
        http_client = Client()
        client = RichClient(http_client)
        session = client.session(Request.new(self.get_url('/redirect')))

        status_codes = []

        while not session.done:
            response = yield session.fetch()
            if not status_codes:
                self.assertEqual(
                    RichClientResponseType.redirect, session.response_type)
            status_codes.append(response.status_code)

        self.assertEqual([301, 200], status_codes)
        self.assertTrue(session.done)
        self.assertEqual(RichClientResponseType.normal, session.response_type)
