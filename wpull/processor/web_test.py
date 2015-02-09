import unittest
from wpull.http.request import Request
from wpull.item import URLRecord
from wpull.processor.web import WebProcessorSession
from wpull.url import URLInfo


class TestWeb(unittest.TestCase):
    def test_add_referer(self):
        request = Request()
        url_record = URLRecord(
            url=None,
            status=None,
            try_count=None,
            level=None,
            top_url=None,
            status_code=None,
            referrer='http://example.com/',
            inline=None,
            link_type=None,
            post_data=None,
            filename=None
        )
        url_info = URLInfo.parse('http://example.com/')

        WebProcessorSession._add_referrer(request, url_record, url_info)

        self.assertEqual('http://example.com/', request.fields['Referer'])

    def test_add_referer_https_to_http(self):
        request = Request()
        url_record = URLRecord(
            url=None,
            status=None,
            try_count=None,
            level=None,
            top_url=None,
            status_code=None,
            referrer='https://example.com/',
            inline=None,
            link_type=None,
            post_data=None,
            filename=None
        )
        url_info = URLInfo.parse('http://example.com/image.png')

        WebProcessorSession._add_referrer(request, url_record, url_info)

        self.assertNotIn('referer', request.fields)
