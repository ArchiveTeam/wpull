import io
import unittest


import asyncio
import tornado.testing

from wpull.protocol.http.client import Client
from wpull.protocol.http.request import Request
from wpull.protocol.http.web import WebClient
from wpull.proxy.client import HTTPProxyConnectionPool
from wpull.proxy.server import HTTPProxyServer
import wpull.testing.badapp
import wpull.testing.goodapp
import wpull.testing.async



class Mixin:
    @wpull.testing.async.async_test()
    def test_basic_requests(self):
        proxy_http_client = Client()
        proxy_server = HTTPProxyServer(proxy_http_client)
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        yield from asyncio.start_server(proxy_server, sock=proxy_socket)

        connection_pool = HTTPProxyConnectionPool(('127.0.0.1', proxy_port))
        http_client = Client(connection_pool=connection_pool)

        for dummy in range(3):
            with http_client.session() as session:
                response = yield from session.start(Request(self.get_url('/')))
                self.assertEqual(200, response.status_code)

                file = io.BytesIO()
                yield from session.download(file=file)
                data = file.getvalue().decode('ascii', 'replace')
                self.assertTrue(data.endswith('</html>'))

            with http_client.session() as session:
                response = yield from session.start(Request(
                    self.get_url('/always_error')))
                self.assertEqual(500, response.status_code)
                self.assertEqual('Dragon In Data Center', response.reason)

                file = io.BytesIO()
                yield from session.download(file=file)
                data = file.getvalue().decode('ascii', 'replace')
                self.assertEqual('Error', data)


class TestProxy(wpull.testing.goodapp.GoodAppTestCase, Mixin):
    pass


class TestProxySSL(wpull.testing.goodapp.GoodAppHTTPSTestCase, Mixin):
    pass

