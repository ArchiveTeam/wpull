# encoding=utf-8
# 2to3 bug, python version 2.6, 2.7.3: http.server line must not be at top
import abc
import http.server
import logging
import threading
import time
import tornado.gen
from tornado.testing import AsyncTestCase

from wpull.http import Connection, Request
from wpull.recorder import DebugPrintRecorder


_logger = logging.getLogger(__name__)
_dummy = abc


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._routes = {
            '/': self.basic,
            '/content_length': self.basic_content_length,
            '/chunked': self.basic_chunked,
            '/chunked_trailer': self.basic_chunked_trailer,
            '/underrun': self.underrun_response,
            '/overrun': self.overrun_response,
            '/malformed_chunked': self.malformed_chunked,
            '/buffer_overflow': self.buffer_overflow,
            '/bad_chunk_size': self.bad_chunk_size,
            '/content_length_and_chunked': self.content_length_and_chunked,
            '/bad_header_deliminators': self.bad_header_deliminators,
            '/utf8_header': self.utf8_header,
            '/sleep_short': self.sleep_short,
            '/sleep_long': self.sleep_long,
            '/short_close': self.short_close,
        }
        http.server.BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def do_GET(self):
        _logger.debug('do_GET here')
        route = self._routes[self.path]
        route()
        _logger.debug('do_GET done')

    def basic(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'hello world!')

    def basic_content_length(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * length)

    def basic_chunked(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-ENCODING', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n7\r\n world!\r\n0\r\n\r\n')

    def basic_chunked_trailer(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n0007\r\n world!\r\n0\r\nAnimal: dolphin\r\n\r\n')

    def underrun_response(self):
        length = 100
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * (length // 2))

    def overrun_response(self):
        length = 100
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * (length * 2))

    def malformed_chunked(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n5\r\n world!\r\n0\r\n\r\n')

    def buffer_overflow(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        while True:
            self.wfile.write(b'0' * 1000)

    def bad_chunk_size(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        self.wfile.write(b'FAIL\r\nHello world!')

    def content_length_and_chunked(self):
        self.protocol_version = 'HTTP/1.1'
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.send_header('content-length', '42')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n7\r\n world!\r\n0\r\n\r\n')

    def bad_header_deliminators(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: 3\n')
        self.wfile.write(b'\n')
        self.wfile.write(b'hi\n')

    def utf8_header(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: 3\r\n')
        self.wfile.write('Whoa: 🐱\r\n'.encode('utf-8'))
        self.wfile.write(b'\r\n')
        self.wfile.write(b'hi\n')

    def sleep_short(self):
        self.send_response(200)
        self.send_header('content-length', '2')
        self.end_headers()
        self.wfile.write(b'1')
        time.sleep(0.1)
        self.wfile.write(b'2')

    def sleep_long(self):
        self.send_response(200)
        self.send_header('content-length', '2')
        self.end_headers()
        self.wfile.write(b'1')
        time.sleep(2)
        self.wfile.write(b'2')

    def short_close(self):
        self.send_response(200)
        self.send_header('content-length', '100')
        self.end_headers()
        self.wfile.write(b'1')
        self.close_connection = 1


class Server(threading.Thread):
    def __init__(self, port=0):
        threading.Thread.__init__(self)
        self.daemon = True
        self._port = port
        self._server = None
        self._server = http.server.HTTPServer(
            ('localhost', self._port), Handler)
        self._port = self._server.server_address[1]
        _logger.debug(
            'Server bound to {0}'.format(self._server.server_address))

    def run(self):
        self._server.serve_forever()

    def stop(self):
        self._server.shutdown()

    @property
    def port(self):
        return self._port


class BadAppTestCase(AsyncTestCase):
    def setUp(self):
        super().setUp()
        self.http_server = Server()
        self.http_server.start()
        self._port = self.http_server.port
        self.connection = Connection('localhost', self._port,
            connect_timeout=2.0, read_timeout=4.0)

    @tornado.gen.coroutine
    def fetch(self, path):
        response = yield self.connection.fetch(Request.new(self.get_url(path)),
            DebugPrintRecorder())
        raise tornado.gen.Return(response)

    def get_http_port(self):
        return self._port

    def get_protocol(self):
        return 'http'

    def get_url(self, path):
        # from tornado.testing
        return '%s://localhost:%s%s' % (self.get_protocol(),
                                        self.get_http_port(), path)

    def tearDown(self):
        self.http_server.stop()
        super().tearDown()

if __name__ == '__main__':
    server = Server(8888)
    server.start()
    server.join()
