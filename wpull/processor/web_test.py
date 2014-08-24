import unittest
from wpull.processor.web import WebProcessorSession


class TestProcessor(unittest.TestCase):
    def test_web_processor_parse_url(self):
        self.assertTrue(
            WebProcessorSession.parse_url('http://example.com')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('http://')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('')
        )
        self.assertFalse(
            WebProcessorSession.parse_url('.xn--hda.com/')
        )
