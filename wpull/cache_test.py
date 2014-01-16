import time

from wpull.backport.testing import unittest
from wpull.cache import Cache


class TestCache(unittest.TestCase):
    def test_size(self):
        cache = Cache(max_items=2)

        cache['a'] = 1
        cache['b'] = 2

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])
        self.assertIn('b', cache)
        self.assertEqual(2, cache['b'])

        cache['c'] = 3

        self.assertIn('c', cache)
        self.assertEqual(3, cache['c'])
        self.assertNotIn('a', cache)
        self.assertIn('b', cache)
        self.assertEqual(2, cache['b'])

    def test_expire(self):
        cache = Cache(time_to_live=0.1)

        cache['a'] = 1

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])

        time.sleep(0.2)

        self.assertNotIn('a', cache)
