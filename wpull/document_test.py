# encoding=utf-8
import io

from wpull.backport.testing import unittest
from wpull.document import CSSReader


class DocumentTest(unittest.TestCase):
    def test_basic_css_parse(self):
        code = io.BytesIO(b'body { font-size: 100px; }')
        css_reader = CSSReader()
        stylesheet = css_reader.parse(code)

        rule = list(stylesheet)[0]
        self.assertEqual(rule.STYLE_RULE, rule.type)
        self.assertEqual('body', rule.selectorList[0].selectorText)
        self.assertEqual('100px', rule.style['font-size'])
