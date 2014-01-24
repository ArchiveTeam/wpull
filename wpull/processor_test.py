import unittest
from wpull.processor import WebProcessorSession


class TestProcessor(unittest.TestCase):
    def test_web_processor_parse_url(self):
        self.assertTrue(
            WebProcessorSession._parse_url('http://example.com', 'utf-8')
        )
        self.assertFalse(
            WebProcessorSession._parse_url('http://', 'utf-8')
        )
        self.assertFalse(
            WebProcessorSession._parse_url('', 'utf-8')
        )
