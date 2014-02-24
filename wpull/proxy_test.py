# encoding=utf-8
import logging
import tornado.curl_httpclient
import tornado.httpclient
import tornado.testing

from wpull.http import Client
from wpull.proxy import HTTPProxyServer
from wpull.recorder import DebugPrintRecorder
import wpull.testing.goodapp


_logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30


class TestProxy(wpull.testing.goodapp.GoodAppTestCase):
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
            proxy_port=proxy_port
        )

        response = yield test_client.fetch(request)

        self.assertEqual(200, response.code)
        self.assertIn(b'Hello!', response.body)
