import tornado.testing
import unittest

from wpull.util import (to_bytes, sleep, to_str, datetime_str, OrderedDefaultDict,
    wait_future, TimedOut)


class TestUtil(unittest.TestCase):
    def test_to_bytes(self):
        self.assertEqual(b'hi', to_bytes('hi'))
        self.assertEqual([b'hi'], to_bytes(['hi']))

    def test_to_str(self):
        self.assertEqual('hi', to_str(b'hi'))
        self.assertEqual(['hi'], to_str([b'hi']))

    def test_datetime_str(self):
        self.assertEqual(20, len(datetime_str()))

    def test_ordered_default_dict(self):
        mapping = OrderedDefaultDict(lambda: 2)
        mapping['a'] += 4
        mapping['b'] += 3
        mapping['c'] += 2

        self.assertEqual(
            [('a', 6), ('b', 5), ('c', 4)],
            list(mapping.items())
        )


class TestUtilAsync(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_sleep(self):
        yield sleep(1.0)

    @tornado.testing.gen_test
    def test_wait_future(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(60.0)

        try:
            yield wait_future(test_func(), 0.1)
        except TimedOut:
            pass
        else:
            self.assertTrue(False)
