import unittest
from wpull.processor import WebProcessorSession


class TestProcessor(unittest.TestCase):
    def test_web_processor_parse_url(self):
        self.assertTrue(
            WebProcessorSession.parse_url('http://example.com', 'utf-8')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('http://', 'utf-8')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('', 'utf-8')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('.xn--hda.com/', 'utf-8')
        )
