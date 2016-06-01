# encoding=utf-8
import logging
import unittest


import tornado.httpclient
import tornado.testing
import asyncio

from wpull.cookie import BetterMozillaCookieJar, DeFactoCookiePolicy
from wpull.protocol.http.client import Client
from wpull.proxy.server import HTTPProxyServer, HTTPProxySession
from wpull.cookiewrapper import CookieJarWrapper
import wpull.testing.badapp
import wpull.testing.goodapp
import wpull.testing.async


try:
    import pycurl
    import tornado.curl_httpclient
except ImportError:
    pycurl = None
    tornado.curl_httpclient = None


_logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30


class TestProxy(wpull.testing.goodapp.GoodAppTestCase):
    # TODO: fix Travis CI to install pycurl
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        cookie_jar = BetterMozillaCookieJar()
        policy = DeFactoCookiePolicy(cookie_jar=cookie_jar)
        cookie_jar.set_policy(policy)
        cookie_jar_wrapper = CookieJarWrapper(cookie_jar)

        http_client = Client()
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        client_request = None

        def request_callback(client_request_):
            nonlocal client_request
            client_request = client_request_
            print('client request', client_request)
            cookie_jar_wrapper.add_cookie_header(client_request)

        def server_response_callback(server_response):
            print('server response', server_response)
            assert client_request
            cookie_jar_wrapper.extract_cookies(server_response, client_request)

        def new_sesssion_callback(session: HTTPProxySession):
            session.event_dispatcher.add_listener(
                HTTPProxySession.Event.client_request, request_callback)
            session.event_dispatcher.add_listener(
                HTTPProxySession.Event.server_end_response,
                server_response_callback)

        proxy.event_dispatcher.add_listener(
            HTTPProxyServer.Event.begin_session, new_sesssion_callback)

        yield from asyncio.start_server(proxy, sock=proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
        )

        response = yield from tornado_future_adapter(test_client.fetch(request))

        self.assertEqual(200, response.code)
        self.assertIn(b'Hello!', response.body)
        cookies = tuple(cookie_jar)
        self.assertEqual('hi', cookies[0].name)
        self.assertEqual('hello', cookies[0].value)

    # TODO: fix Travis CI to install pycurl
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_post(self):
        http_client = Client()
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        yield from asyncio.start_server(proxy, sock=proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/post/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
            body='text=blah',
            method='POST'
        )

        response = yield from tornado_future_adapter(test_client.fetch(request))

        self.assertEqual(200, response.code)
        self.assertIn(b'OK', response.body)


class TestProxy2(wpull.testing.badapp.BadAppTestCase):
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        http_client = Client()
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        yield from asyncio.start_server(proxy, sock=proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/no_content'),
            proxy_host='localhost',
            proxy_port=proxy_port
        )

        response = yield from tornado_future_adapter(test_client.fetch(request))

        self.assertEqual(204, response.code)


@asyncio.coroutine
def tornado_future_adapter(future):
    event = asyncio.Event()

    future.add_done_callback(lambda dummy: event.set())

    yield from event.wait()

    return future.result()
