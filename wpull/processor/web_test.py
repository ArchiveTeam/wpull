import unittest

from wpull.pipeline.item import URLRecord
from wpull.processor.web import WebProcessorSession
from wpull.protocol.http.request import Request


class TestWeb(unittest.TestCase):
    def test_add_referer(self):
        request = Request()
        url_record = URLRecord()
        url_record.parent_url = 'http://example.com/'
        url_record.url = 'http://example.com/image.png'

        WebProcessorSession._add_referrer(request, url_record)

        self.assertEqual('http://example.com/', request.fields['Referer'])

    def test_add_referer_https_to_http(self):
        request = Request()
        url_record = URLRecord()
        url_record.parent_url = 'https://example.com/'
        url_record.url = 'http://example.com/image.png'

        WebProcessorSession._add_referrer(request, url_record)

        self.assertNotIn('referer', request.fields)
