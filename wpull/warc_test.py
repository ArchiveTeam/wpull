# encoding=utf-8

import io
import unittest

from wpull.warc import read_cdx


class TestWARC(unittest.TestCase):
    def test_read_cdx(self):
        data = io.BytesIO(b' CDX a A b\nhi hello foxes?\n')
        for record in read_cdx(data, encoding='ascii'):
            self.assertEqual(record['a'], 'hi')
            self.assertEqual(record['A'], 'hello')
            self.assertEqual(record['b'], 'foxes?')
