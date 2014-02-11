import io
import tornado.testing

from wpull.http import Response, Request
from wpull.robotstxt import RobotsTxtPool, RobotsState, RobotsDenied
from wpull.web import RichClient, RobotsTxtRichClientSession


class MockHTTPClient(object):
    def __init__(self):
        self.response = None

    @tornado.gen.coroutine
    def fetch(self, request, **kwargs):
        raise tornado.gen.Return(self.response)


class MockRobotsTxtRichClientSession(RobotsTxtRichClientSession):
    pass


class TestRobotsTxtRichClient(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_fetch_allow(self):
        http_client = MockHTTPClient()
        pool = RobotsTxtPool()
        client = RichClient(http_client, pool)
        session = MockRobotsTxtRichClientSession(
            client, Request.new('http://example.com')
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
            client, Request.new('http://example.com')
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
            client, Request.new('http://example.com')
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
