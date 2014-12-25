import unittest

from wpull.driver.resource import PhantomJSResourceTracker


class TestResource(unittest.TestCase):
    def test_phantomjs_resource_tracker(self):
        tracker = PhantomJSResourceTracker()

        self.assertFalse(tracker.resources)
        self.assertEqual(0, len(tracker.pending))
        self.assertEqual(0, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))

        tracker.process_request({'id': 1, 'url': 'http://example.com/'})

        self.assertEqual(1, len(tracker.pending))
        self.assertEqual(0, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))

        tracker.process_response({'id': 1, 'stage': 'start'})
        tracker.process_response({'id': 1, 'stage': 'start'})

        self.assertEqual(1, len(tracker.pending))
        self.assertEqual(0, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))

        tracker.process_response({'id': 1, 'stage': 'end'})

        self.assertEqual(0, len(tracker.pending))
        self.assertEqual(1, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))

        tracker.process_request({'id': 2, 'url': 'http://example.com/'})

        self.assertEqual(1, len(tracker.pending))
        self.assertEqual(1, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))

        tracker.process_error({'id': 2})

        self.assertEqual(0, len(tracker.pending))
        self.assertEqual(1, len(tracker.loaded))
        self.assertEqual(1, len(tracker.error))

        tracker.reset()

        self.assertFalse(tracker.resources)
        self.assertEqual(0, len(tracker.pending))
        self.assertEqual(0, len(tracker.loaded))
        self.assertEqual(0, len(tracker.error))
