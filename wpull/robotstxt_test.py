import unittest

from wpull.database import URLRecord, Status
from wpull.engine import URLItem
from wpull.http import Request, Response
from wpull.robotstxt import RobotsTxtSessionMixin
from wpull.url import URLInfo
import io
from wpull.processor import WebProcessorSession
from wpull.waiter import LinearWaiter


class MockWebProcessorSession(WebProcessorSession):
    def __init__(self, url_item, should_fetch=True):
        super().__init__(url_item, None, None,
            None, LinearWaiter(), None, Request.new,
            False, False, 5)
        self._should_fetch = should_fetch

    def should_fetch(self):
        return self._should_fetch

    def _handle_document(self, response):
        return True


class MockURLRecord(object):
    def __init__(self):
        self.url = 'http://example.com/'
        self.referrer = None


class MockURLTable(object):
    def __init__(self):
        self.status = None

    def update(self, url, **kwargs):
        self.status = kwargs.pop('status', None)


class MockWebProcessorWithRobotsTxtSession(
RobotsTxtSessionMixin, MockWebProcessorSession):
    pass


class TestRobotsTxt(unittest.TestCase):
    def test_fetch_false(self):
        url_item = URLItem(
            None,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=False
        )

        self.assertFalse(session.should_fetch())

    def test_fetch_allow(self):
        url_item = URLItem(
            None,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True
        )

        self.assertTrue(session.should_fetch())

        request = session.new_request()

        self.assertTrue(request.url_info.url.endswith('robots.txt'))

        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')

        self.assertFalse(session.handle_response(response))
        self.assertTrue(session.should_fetch())

        request = session.new_request()

        self.assertTrue(request.url_info.url.endswith('/'))

    def test_fetch_disallow(self):
        mock_url_table = MockURLTable()
        url_item = URLItem(
            mock_url_table,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True
        )

        self.assertTrue(session.should_fetch())

        request = session.new_request()

        self.assertTrue(request.url_info.url.endswith('robots.txt'))

        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nDisallow: /\n')

        self.assertFalse(session.handle_response(response))
        self.assertFalse(session.should_fetch())
        self.assertEqual(Status.skipped, mock_url_table.status)

    def test_fetch_allow_redirects(self):
        url_item = URLItem(
            MockURLTable(),
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True
        )

        # Try fetch example.com/ (need robots.txt)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://example.com/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.com/robots.txt'
        self.assertFalse(session.handle_response(response))

        # Try fetch www.example.com/robots.txt
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://www.example.com/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.net/robots.txt'
        self.assertFalse(session.handle_response(response))

        # Try fetch www.example.net/robots.txt
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://www.example.net/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')
        self.assertFalse(session.handle_response(response))

        # Try fetch example.com/ (robots.txt already fetched)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://example.com/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.com/'
        self.assertFalse(session.handle_response(response))

        # Try www.example.com/ (robots.txt already fetched)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://www.example.com/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.net/'
        self.assertFalse(session.handle_response(response))

        # Try www.example.net/ (robots.txt already fetched)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://www.example.net/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://lol.example.net/'
        self.assertFalse(session.handle_response(response))

        # Try lol.example.net/ (need robots.txt)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://lol.example.net/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')
        self.assertFalse(session.handle_response(response))

        # Try lol.example.net/ (robots.txt already fetched)
        self.assertTrue(session.should_fetch())
        request = session.new_request()
        self.assertEqual(
            'http://lol.example.net/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        self.assertTrue(session.handle_response(response))
