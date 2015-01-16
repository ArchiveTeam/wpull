import unittest
from wpull.url import URLInfo
from wpull.urlrewrite import URLRewriter


class TestURLRewrite(unittest.TestCase):
    def test_rewriter(self):
        rewriter = URLRewriter()

        self.assertEquals(
            'http://example.com/',
            rewriter.rewrite(URLInfo.parse('http://example.com/')).url
        )
        self.assertEquals(
            'http://example.com/',
            rewriter.rewrite(URLInfo.parse('http://example.com/#hashtag!')).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse('https://groups.google.com/forum/#!forum/python-tulip')).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?stupid_hash_fragments&_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse(
                'https://groups.google.com/forum/?stupid_hash_fragments#!forum/python-tulip'
            )).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?stupid_hash_fragments=farts&_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse(
                'https://groups.google.com/forum/?stupid_hash_fragments=farts#!forum/python-tulip'
            )).url
        )
