import tornado.testing
import unittest

from wpull.util import to_bytes, sleep, to_str


class TestUtil(unittest.TestCase):
    def test_to_bytes(self):
        self.assertEqual(b'hi', to_bytes('hi'))
        self.assertEqual([b'hi'], to_bytes(['hi']))

    def test_to_str(self):
        self.assertEqual('hi', to_str(b'hi'))
        self.assertEqual(['hi'], to_str([b'hi']))


class TestUtilAsync(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_sleep(self):
        yield sleep(1.0)
