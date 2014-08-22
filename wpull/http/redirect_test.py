# encoding=utf-8
import unittest

from wpull.http.redirect import RedirectTracker
from wpull.http.request import Response


class TestWeb(unittest.TestCase):
    def test_redirect_tracker(self):
        tracker = RedirectTracker(5)

        self.assertFalse(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertFalse(tracker.next_location(raw=True))
        self.assertEqual(0, tracker.count())

        response = Response(200, 'OK')

        tracker.load(response)

        self.assertFalse(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertFalse(tracker.next_location())
        self.assertEqual(0, tracker.count())

        response = Response(303, 'See other')
        response.fields['location'] = '/test'

        tracker.load(response)

        self.assertTrue(tracker.is_redirect())
        self.assertFalse(tracker.is_repeat())
        self.assertFalse(tracker.exceeded())
        self.assertEqual('/test', tracker.next_location(raw=True))
        self.assertEqual(1, tracker.count())

        response = Response(307, 'Temporary redirect')
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
