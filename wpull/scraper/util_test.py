import unittest

from wpull.scraper.util import clean_link_soup, parse_refresh


class TestUtil(unittest.TestCase):
    def test_clean_link_soup(self):
        self.assertEqual(
            'http://example.com',
            clean_link_soup('http://example.com  ')
        )
        self.assertEqual(
            'http://example.com/',
            clean_link_soup('\n\r\thttp://example.com\n\r\r\r\n\t/')
        )
        self.assertEqual(
            'http://example.com/ something',
            clean_link_soup('http://example.com\n\t / something  \n\r\t')
        )
        self.assertEqual(
            'http://example.com/dog cat/',
            clean_link_soup('http://example.com/\n dog \tcat\r/\n')
        )
        self.assertEqual(
            'ßðf ¤Jáßðff ßðfœ³²œ¤ œë ßfœ',
            clean_link_soup('ß\tðf ¤Jáßðf\n f ßðfœ³²œ¤ œë ßfœ ')
        )

    def test_parse_refresh(self):
        self.assertEqual(
            'http://example.com', parse_refresh('10;url="http://example.com"')
        )
        self.assertEqual(
            'http://example.com', parse_refresh('10;url= http://example.com ')
        )
        self.assertEqual(
            'example.com', parse_refresh("url =' example.com '")
        )
        self.assertFalse(
            parse_refresh('url=')
        )
        self.assertFalse(
            parse_refresh('url =     ')
        )
