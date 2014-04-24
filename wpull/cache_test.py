import time

from wpull.backport.testing import unittest
from wpull.cache import FIFOCache, LRUCache


class TestCache(unittest.TestCase):
    def test_fifo_size(self):
        cache = FIFOCache(max_items=2)

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

    def test_fifo_expire(self):
        cache = FIFOCache(time_to_live=0.1)

        cache['a'] = 1

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])

        time.sleep(0.2)

        self.assertNotIn('a', cache)

    def test_lru_size_1(self):
        cache = LRUCache(max_items=2)

        cache['a'] = 1
        cache['b'] = 2

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])
        self.assertIn('b', cache)
        self.assertEqual(2, cache['b'])

        # Touch by access!
        time.sleep(0.01)
        dummy = cache['a']

        cache['c'] = 3

        self.assertIn('c', cache)
        self.assertEqual(3, cache['c'])
        self.assertNotIn('b', cache)
        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])

    def test_lru_size_2(self):
        cache = LRUCache(max_items=2)

        cache['a'] = 1
        cache['b'] = 2

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])
        self.assertIn('b', cache)
        self.assertEqual(2, cache['b'])

        # Touch by assignment!
        time.sleep(0.01)
        cache['a'] = 1

        cache['c'] = 3

        self.assertIn('c', cache)
        self.assertEqual(3, cache['c'])
        self.assertNotIn('b', cache)
        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])

    def test_lru_expire(self):
        cache = LRUCache(time_to_live=0.1)

        cache['a'] = 1

        self.assertIn('a', cache)
        self.assertEqual(1, cache['a'])

        time.sleep(0.2)

        self.assertNotIn('a', cache)
