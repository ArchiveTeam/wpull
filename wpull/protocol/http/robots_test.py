# encoding=utf-8
import contextlib
import io

import asyncio

from wpull.errors import ProtocolError, ServerError
from wpull.protocol.http.request import Request, Response
from wpull.protocol.http.robots import RobotsTxtChecker, NotInPoolError
import wpull.testing.async


class MockWebClient(object):
    def __init__(self):
        self.mock_response_callback = None
        self.request = None
        self.session_obj = None

    def session(self, request):
        self.request = request
        self.session_obj = MockWebSession(self)
        return self.session_obj


class MockWebSession(object):
    def __init__(self, client):
        self.client = client
        self.done_value = None

    def done(self):
        return self.done_value

    @asyncio.coroutine
    def start(self):
        return self.client.mock_response_callback(self.client.request)

    @asyncio.coroutine
    def download(self, file=None):
        pass


class TestRobots(wpull.testing.async.AsyncTestCase):
    @wpull.testing.async.async_test
    def test_fetch_allow(self):
        checker = RobotsTxtChecker(web_client=MockWebClient())
        request = Request('http://example.com')
        request.prepare_for_send()

        self.assertRaises(NotInPoolError, checker.can_fetch_pool, request)

        def response_callback(request):
            request.prepare_for_send()
            self.assertTrue(request.url_info.url.endswith('robots.txt'))
            response = Response(200, 'OK')
            response.request = request
            response.body = io.StringIO('User-agent:*\nAllow: /\n')
            checker.web_client.session_obj.done_value = True
            return response

        checker.web_client.mock_response_callback = response_callback

        yield from checker.fetch_robots_txt(request)

        self.assertTrue(checker.can_fetch_pool(request))
        self.assertTrue((yield from checker.can_fetch(request)))

    @wpull.testing.async.async_test
    def test_fetch_disallow(self):
        checker = RobotsTxtChecker(web_client=MockWebClient())
        request = Request('http://example.com')
        request.prepare_for_send()

        self.assertRaises(NotInPoolError, checker.can_fetch_pool, request)

        def response_callback(request):
            request.prepare_for_send()
            self.assertTrue(request.url_info.url.endswith('robots.txt'))
            response = Response(200, 'OK')
            response.request = request
            response.body = io.StringIO('User-agent:*\nDisallow: /\n')
            checker.web_client.session_obj.done_value = True
            return response

        checker.web_client.mock_response_callback = response_callback

        yield from checker.fetch_robots_txt(request)

        self.assertFalse(checker.can_fetch_pool(request))
        self.assertFalse((yield from checker.can_fetch(request)))

    @wpull.testing.async.async_test
    def test_redirect_loop(self):
        checker = RobotsTxtChecker(web_client=MockWebClient())
        request = Request('http://example.com')
        request.prepare_for_send()

        nonlocal_dict = {'counter': 0}

        def response_callback(request):
            request.prepare_for_send()
            self.assertTrue(request.url_info.url.endswith('robots.txt'))
            response = Response(302, 'See else')
            response.request = request
            response.fields['Location'] = '/robots.txt'

            nonlocal_dict['counter'] += 1

            if nonlocal_dict['counter'] > 20:
                raise ProtocolError('Mock redirect loop error.')

            return response

        checker.web_client.mock_response_callback = response_callback

        self.assertTrue((yield from checker.can_fetch(request)))
        self.assertTrue(checker.can_fetch_pool(request))

    @wpull.testing.async.async_test
    def test_server_error(self):
        checker = RobotsTxtChecker(web_client=MockWebClient())
        request = Request('http://example.com')
        request.prepare_for_send()

        def response_callback(request):
            request.prepare_for_send()
            self.assertTrue(request.url_info.url.endswith('robots.txt'))
            response = Response(500, 'Oops')
            response.request = request
            checker.web_client.session_obj.done_value = True
            return response

        checker.web_client.mock_response_callback = response_callback

        try:
            yield from checker.can_fetch(request)
        except ServerError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test
    def test_fetch_allow_redirects(self):
        checker = RobotsTxtChecker(web_client=MockWebClient())
        request = Request('http://example.com')
        request.prepare_for_send()

        # Try fetch example.com/ (need robots.txt)
        def response_callback_1(request):
            request.prepare_for_send()
            self.assertEqual('http://example.com/robots.txt',
                             request.url_info.url)

            response = Response(301, 'Moved')
            response.fields['location'] = 'http://www.example.com/robots.txt'
            response.request = request

            checker.web_client.mock_response_callback = response_callback_2
            checker.web_client.request = Request(
                'http://www.example.com/robots.txt')

            return response

        # Try fetch www.example.com/robots.txt
        def response_callback_2(request):
            request.prepare_for_send()
            self.assertEqual('http://www.example.com/robots.txt',
                             request.url_info.url)

            response = Response(301, 'Moved')
            response.fields['location'] = 'http://www.example.net/robots.txt'
            response.request = request

            checker.web_client.mock_response_callback = response_callback_3
            checker.web_client.request = Request(
                'http://www.example.net/robots.txt')

            return response

        # Try fetch www.example.net/robots.txt
        def response_callback_3(request):
            request.prepare_for_send()
            self.assertEqual('http://www.example.net/robots.txt',
                             request.url_info.url)

            response = Response(200, 'OK')
            response.request = request
            response.body = io.StringIO('User-agent:*\nAllow: /\n')

            checker.web_client.session_obj.done_value = True
            return response

        checker.web_client.mock_response_callback = response_callback_1

        self.assertTrue((yield from checker.can_fetch(request)))
        self.assertTrue(checker.can_fetch_pool(request))
