# encoding=utf-8
import logging
import tornado.httpclient
import tornado.testing

from wpull.backport.testing import unittest
from wpull.http.client import Client
from wpull.proxy import HTTPProxyServer
from wpull.recorder import DebugPrintRecorder
import wpull.testing.goodapp
import wpull.testing.badapp


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
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client, io_loop=self.io_loop)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()
        proxy.add_socket(proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
        )

        response = yield test_client.fetch(request)

        self.assertEqual(200, response.code)
        self.assertIn(b'Hello!', response.body)

    # TODO: fix Travis CI to install pycurl
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_post(self):
        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client, io_loop=self.io_loop)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()
        proxy.add_socket(proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/post/'),
            proxy_host='localhost',
            proxy_port=proxy_port,
            body='text=blah',
            method='POST'
        )

        response = yield test_client.fetch(request)

        self.assertEqual(200, response.code)
        self.assertIn(b'OK', response.body)


class TestProxy2(wpull.testing.badapp.BadAppTestCase):
    @unittest.skipIf(pycurl is None, "pycurl module not present")
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        http_client = Client(recorder=DebugPrintRecorder())
        proxy = HTTPProxyServer(http_client, io_loop=self.io_loop)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()
        proxy.add_socket(proxy_socket)

        _logger.debug('Proxy on port {0}'.format(proxy_port))

        test_client = tornado.curl_httpclient.CurlAsyncHTTPClient()

        request = tornado.httpclient.HTTPRequest(
            self.get_url('/no_content'),
            proxy_host='localhost',
            proxy_port=proxy_port
        )

        response = yield test_client.fetch(request)

        self.assertEqual(204, response.code)
