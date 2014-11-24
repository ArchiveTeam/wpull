import unittest

from wpull.processor.rule import ProcessingRule


class TestRule(unittest.TestCase):
    def test_parse_url_no_crash(self):
        self.assertTrue(
            ProcessingRule.parse_url('http://example.com')
        )
        self.assertFalse(
            ProcessingRule.parse_url('http://')
        )
        self.assertFalse(
            ProcessingRule.parse_url('')
        )
        self.assertFalse(
            ProcessingRule.parse_url('.xn--hda.com/')
        )
