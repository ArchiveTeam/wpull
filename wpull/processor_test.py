import unittest
from wpull.processor import WebProcessorSession


class TestProcessor(unittest.TestCase):
    def test_web_processor_parse_url(self):
        self.assertTrue(
            WebProcessorSession._parse_url('http://example.com')
        )
        self.assertFalse(
            WebProcessorSession._parse_url('http://')
        )
        self.assertFalse(
            WebProcessorSession._parse_url('')
        )
