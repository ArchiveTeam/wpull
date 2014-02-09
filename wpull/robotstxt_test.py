import io
import tornado.testing
import unittest

from wpull.database import Status
from wpull.engine import URLItem
from wpull.http import (Response, Request, RedirectTracker, RichClientSession,
    RichClient)
from wpull.processor import WebProcessorSession, WebProcessor
from wpull.robotstxt import (RobotsTxtSessionMixin, RobotsTxtPool,
    RobotsTxtRichClientSessionMixin, RobotsState, RobotsDenied)
from wpull.url import URLInfo


class MockWebProcessorSession(WebProcessorSession):
    def __init__(self, url_item, should_fetch=True):
        super().__init__(
            WebProcessor(),
            url_item,
        )
        self._should_fetch = should_fetch

    def should_fetch(self):
        return self._should_fetch

    def _handle_document(self, response):
        return True


class MockURLRecord(object):
    def __init__(self):
        self.url = 'http://example.com/'
        self.referrer = None
        self.post_data = None


class MockURLTable(object):
    def __init__(self):
        self.status = None

    def update(self, url, **kwargs):
        self.status = kwargs.pop('status', None)


class MockWebProcessorWithRobotsTxtSession(
RobotsTxtSessionMixin, MockWebProcessorSession):
    pass


class MockHTTPClient(object):
    def __init__(self):
        self.response = None

    @tornado.gen.coroutine
    def fetch(self, request, **kwargs):
        raise tornado.gen.Return(self.response)


class MockRobotsTxtRichClientSession(
RobotsTxtRichClientSessionMixin, RichClientSession):
    pass


class TestRobotsTxt(unittest.TestCase):
    def test_fetch_false(self):
        pool = RobotsTxtPool()
        url_item = URLItem(
            None,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=False,
            robots_txt_pool=pool,
        )

        self.assertFalse(session.should_fetch())

    def test_fetch_allow(self):
        pool = RobotsTxtPool()
        url_item = URLItem(
            None,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True,
            robots_txt_pool=pool,
        )

        self.assertTrue(session.should_fetch())

        request = session.new_request()

        self.assertTrue(request.url_info.url.endswith('robots.txt'))

        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')

        self.assertFalse(session.handle_response(response))
        self.assertTrue(session.should_fetch())

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True,
            robots_txt_pool=pool,
        )

        request = session.new_request()

        self.assertTrue(request.url_info.url.endswith('/'))

    def test_fetch_disallow(self):
        pool = RobotsTxtPool()
        mock_url_table = MockURLTable()
        url_item = URLItem(
            mock_url_table,
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True,
            robots_txt_pool=pool,
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
        pool = RobotsTxtPool()
        url_item = URLItem(
            MockURLTable(),
            URLInfo.parse('http://example.com/'),
            MockURLRecord()
        )

        session = MockWebProcessorWithRobotsTxtSession(
            url_item,
            should_fetch=True,
            robots_txt_pool=pool,
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


class TestRobotsTxtRichClient(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_fetch_allow(self):
        http_client = MockHTTPClient()
        pool = RobotsTxtPool()
        client = RichClient(http_client, pool)
        session = MockRobotsTxtRichClientSession(
            client, Request.new('http://example.com'), {}
        )

        self.assertEqual(RobotsState.unknown, session._robots_state)

        request = session.next_request
        self.assertTrue(request.url_info.url.endswith('robots.txt'))

        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')

        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        request = session.next_request
        self.assertTrue(request.url_info.url.endswith('/'))

        response = Response('HTTP/1.0', 200, 'OK')
        http_client.response = response
        yield session.fetch()

        self.assertTrue(session.done)

    @tornado.testing.gen_test
    def test_fetch_disallow(self):
        http_client = MockHTTPClient()
        pool = RobotsTxtPool()
        client = RichClient(http_client, pool)
        session = MockRobotsTxtRichClientSession(
            client, Request.new('http://example.com'), {}
        )

        self.assertEqual(RobotsState.unknown, session._robots_state)

        request = session.next_request
        self.assertTrue(request.url_info.url.endswith('robots.txt'))

        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nDisallow: /\n')

        http_client.response = response
        yield session.fetch()

        self.assertEqual(RobotsState.denied, session._robots_state)

        request = session.next_request
        self.assertIsNone(request)

        try:
            yield session.fetch()
        except RobotsDenied:
            pass
        else:
            self.fail()

        self.assertTrue(session.done)

    def test_fetch_allow_redirects(self):
        http_client = MockHTTPClient()
        pool = RobotsTxtPool()
        client = RichClient(http_client, pool)
        session = MockRobotsTxtRichClientSession(
            client, Request.new('http://example.com'), {}
        )

        self.assertEqual(RobotsState.unknown, session._robots_state)

        # Try fetch example.com/ (need robots.txt)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://example.com/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.com/robots.txt'
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.in_progress, session._robots_state)

        # Try fetch www.example.com/robots.txt
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://www.example.com/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.net/robots.txt'
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.in_progress, session._robots_state)

        # Try fetch www.example.net/robots.txt
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://www.example.net/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        # Try fetch example.com/ (robots.txt already fetched)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://example.com/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.com/'
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        # Try www.example.com/ (robots.txt already fetched)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://www.example.com/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://www.example.net/'
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        # Try www.example.net/ (robots.txt already fetched)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://www.example.net/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 301, 'Moved')
        response.fields['location'] = 'http://lol.example.net/'
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        # Try lol.example.net/ (need robots.txt)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://lol.example.net/robots.txt',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        response.body.content_file = io.StringIO('User-agent:*\nAllow: /\n')
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.in_progress, session._robots_state)

        # Try lol.example.net/ (robots.txt already fetched)
        self.assertFalse(session.done)
        request = session.next_request
        self.assertEqual(
            'http://lol.example.net/',
            request.url_info.url
        )
        response = Response('HTTP/1.0', 200, 'OK')
        http_client.response = response
        yield session.fetch()
        self.assertEqual(RobotsState.ok, session._robots_state)

        self.assertTrue(session.done)
