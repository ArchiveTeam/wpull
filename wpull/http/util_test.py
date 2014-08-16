# encoding=utf-8

import unittest

from wpull.http.util import parse_charset, should_close


class TestUtil(unittest.TestCase):
    def test_parse_charset(self):
        self.assertEqual(
            None,
            parse_charset('text/plain')
        )
        self.assertEqual(
            None,
            parse_charset('text/plain; charset=')
        )
        self.assertEqual(
            'utf_8',
            parse_charset('text/plain; charset=utf_8')
        )
        self.assertEqual(
            'UTF-8',
            parse_charset('text/plain; charset="UTF-8"')
        )
        self.assertEqual(
            'Utf8',
            parse_charset("text/plain; charset='Utf8'")
        )
        self.assertEqual(
            'UTF-8',
            parse_charset('text/plain; CHARSET="UTF-8"')
        )

    def test_connection_should_close(self):
        self.assertTrue(should_close('HTTP/1.0', None))
        self.assertTrue(should_close('HTTP/1.0', 'wolf'))
        self.assertTrue(should_close('HTTP/1.0', 'close'))
        self.assertTrue(should_close('HTTP/1.0', 'ClOse'))
        self.assertFalse(should_close('HTTP/1.0', 'keep-Alive'))
        self.assertFalse(should_close('HTTP/1.0', 'keepalive'))
        self.assertTrue(should_close('HTTP/1.1', 'close'))
        self.assertTrue(should_close('HTTP/1.1', 'ClOse'))
        self.assertFalse(should_close('HTTP/1.1', 'dragons'))
        self.assertFalse(should_close('HTTP/1.1', 'keep-alive'))
        self.assertTrue(should_close('HTTP/1.2', 'close'))
