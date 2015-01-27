# encoding=utf-8
import logging
import unittest

from trollius import From, Return
import tornado.httpclient
import tornado.testing
import trollius

from wpull.cookie import RelaxedMozillaCookieJar, DeFactoCookiePolicy
from wpull.http.client import Client
from wpull.proxy import HTTPProxyServer
from wpull.recorder.printing import DebugPrintRecorder
from wpull.wrapper import CookieJarWrapper
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
        cookie_jar = RelaxedMozillaCookieJar()
        policy = DeFactoCookiePolicy(cookie_jar=cookie_jar)
        cookie_jar.set_policy(policy)
        cookie_jar_wrapper = CookieJarWrapper(cookie_jar)

        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        def request_callback(request):
            print(request)
            cookie_jar_wrapper.add_cookie_header(request)

        def pre_response_callback(request, response):
            print(response)
            cookie_jar_wrapper.extract_cookies(response, request)

        proxy.request_callback = request_callback
        proxy.pre_response_callback = pre_response_callback

        yield From(trollius.start_server(proxy, sock=proxy_socket))

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
        )

        response = yield From(tornado_future_adapter(test_client.fetch(request)))

        self.assertEqual(200, response.code)
        self.assertIn(b'Hello!', response.body)
        cookies = tuple(cookie_jar)
        self.assertEqual('hi', cookies[0].name)
        self.assertEqual('hello', cookies[0].value)

    # TODO: fix Travis CI to install pycurl
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_post(self):
        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        yield From(trollius.start_server(proxy, sock=proxy_socket))

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/post/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
            body='text=blah',
            method='POST'
        )

        response = yield From(tornado_future_adapter(test_client.fetch(request)))

        self.assertEqual(200, response.code)
        self.assertIn(b'OK', response.body)


class TestProxy2(wpull.testing.badapp.BadAppTestCase):
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        yield From(trollius.start_server(proxy, sock=proxy_socket))

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/no_content'),
            proxy_host='localhost',
            proxy_port=proxy_port
        )

        response = yield From(tornado_future_adapter(test_client.fetch(request)))

        self.assertEqual(204, response.code)


@trollius.coroutine
def tornado_future_adapter(future):
    event = trollius.Event()

    future.add_done_callback(lambda dummy: event.set())

    yield From(event.wait())

    raise Return(future.result())
