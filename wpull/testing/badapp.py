# encoding=utf-8
# 2to3 bug, python version 2.6, 2.7.3: http.server line must not be at top
import abc
import base64
import http.server
import io
import logging
import os.path
import random
import re
import socket
import socketserver
import ssl
import struct
import threading
import time
import zlib

import tornado.ioloop
from tornado.testing import AsyncTestCase as TornadoAsyncTestCase

from gzip import GzipFile
from wpull.testing.async import AsyncTestCase


_logger = logging.getLogger(__name__)
_dummy = abc


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def __init__(self, *args, **kwargs):
        self._routes = {
            '/': self.basic,
            '/content_length': self.basic_content_length,
            '/content_length_with_close': self.basic_content_length_with_close,
            '/content_length_without_close':
                self.basic_content_length_without_close,
            '/chunked': self.basic_chunked,
            '/chunked_trailer': self.basic_chunked_trailer,
            '/chunked_trailer_2': self.basic_chunked_trailer_2,
            '/chunked_non_standard_delim': self.chunked_non_standard_delim,
            '/chunked_with_extension': self.chunked_with_extension,
            '/underrun': self.underrun_response,
            '/overrun': self.overrun_response,
            '/malformed_chunked': self.malformed_chunked,
            '/buffer_overflow': self.buffer_overflow,
            '/buffer_overflow_header': self.buffer_overflow_header,
            '/bad_chunk_size': self.bad_chunk_size,
            '/content_length_and_chunked': self.content_length_and_chunked,
            '/bad_header_deliminators': self.bad_header_deliminators,
            '/utf8_header': self.utf8_header,
            '/sleep_short': self.sleep_short,
            '/sleep_long': self.sleep_long,
            '/short_close': self.short_close,
            '/unclean_8bit_header': self.unclean_8bit_header,
            '/no_colon_header': self.no_colon_header,
            '/malformed_content_length': self.malformed_content_length,
            '/negative_content_length': self.negative_content_length,
            '/big': self.big,
            '/infinite': self.infinite,
            '/gzip_http_1_0': self.gzip_http_1_0,
            '/zlib_http_1_0': self.zlib_http_1_0,
            '/raw_deflate_http_1_0': self.raw_deflate_http_1_0,
            '/gzip_http_1_1': self.gzip_http_1_1,
            '/gzip_chunked': self.gzip_chunked,
            '/zlib_chunked': self.zlib_chunked,
            '/raw_deflate_chunked': self.raw_deflate_chunked,
            '/gzip_corrupt_short': self.gzip_corrupt_short,
            '/gzip_corrupt_footer': self.gzip_corrupt_footer,
            '/bad_cookie': self.bad_cookie,
            '/long_cookie': self.long_cookie,
            '/header_early_close': self.header_early_close,
            '/no_content': self.no_content,
            '/many_links': self.many_links,
            '/non_http_redirect': self.non_http_redirect,
            '/bad_redirect': self.bad_redirect,
            '/bad_redirect_ipv6': self.bad_redirect_ipv6,
            '/utf8_then_binary': self.utf8_then_binary,
            '/false_gzip': self.false_gzip,
            '/status_line_only': self.status_line_only,
            '/newline_line_only': self.newline_line_only,
            '/many_headers': self.many_headers,
        }
        http.server.BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def do_GET(self):
        _logger.debug('do_GET here. path={0}'.format(self.path))
        path = re.match(r'(/[a-zA-Z0-9_]*)', self.path).group(1)
        _logger.debug('do_GET parse path={0}'.format(path))
        route = self._routes[path]
        route()
        _logger.debug('do_GET done. path={0}'.format(self.path))

    def do_HEAD(self):
        self.do_GET()

    def log_message(self, message, *args):
        _logger.debug(message, *args)

    def basic(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'hello world!')
        self.close_connection = True

    def basic_content_length(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * length)

    def basic_content_length_with_close(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(b'a' * length)
        self.close_connection = True

    def basic_content_length_without_close(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * length)
        self.close_connection = True
        time.sleep(0.3)

    def basic_chunked(self):
        self.send_response(200)
        self.send_header('transfer-ENCODING', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n7\r\n world!\r\n0\r\n\r\n')

    def basic_chunked_trailer(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n0007\r\n world!\r\n0\r\nAnimal: dolphin\r\n\r\n')

    def basic_chunked_trailer_2(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(b'5\r\nhello\r\n0007\r\n world!\r\n0\r\n')
        self.wfile.write(b'Animal: dolphin\r\nCake: delicious\r\n\r\n')

    def chunked_non_standard_delim(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\nhello\n0007\n world!\n0\n\n')

    def chunked_with_extension(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5;blah\nhello\r\n7;blah;\r\n world!\r\n0\r\n\r\n')

    def underrun_response(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * (length // 2))

    def overrun_response(self):
        length = 100
        self.send_response(200)
        self.send_header('Content-length', length)
        self.end_headers()
        self.wfile.write(b'a' * (length * 2))

    def malformed_chunked(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()
        self.wfile.write(
            b'5\r\nhello\r\n5\r\n world!\r\n0\r\n\r\n')

    def buffer_overflow(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        for dummy in range(100):
            self.wfile.write(b'0' * 10000)
            time.sleep(0.001)

    def buffer_overflow_header(self):
        self.send_response(200)
        for dummy in range(100):
            self.wfile.write(b'A' * 10000)
        self.wfile.write(b': A\r\n')
        self.end_headers()

    def bad_chunk_size(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        self.wfile.write(b'FAIL\r\nHello world!')

    def content_length_and_chunked(self):
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

    def unclean_8bit_header(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: 3\r\n')
        self.wfile.write('K: Кракозябры\r\n'.encode('koi8-r'))
        self.wfile.write('M: 文字化け\r\n'.encode('shift_jis'))
        self.wfile.write(b'\r\n')
        self.wfile.write(b'hi\n')

    def no_colon_header(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: 3\r\n')
        self.wfile.write(b'Oops\r\n')
        self.wfile.write(b'\r\n')
        self.wfile.write(b'hi\n')

    def malformed_content_length(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: 3-\r\n')
        self.wfile.write(b'\r\n')
        self.wfile.write(b'hi\n')
        self.close_connection = 1

    def negative_content_length(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n')
        self.wfile.write(b'Content-Length: -3\r\n')
        self.wfile.write(b'\r\n')
        self.wfile.write(b'hi\n')
        self.close_connection = 1

    def big(self):
        self.send_response(200)
        self.send_header('Content-length', '10000000')
        self.end_headers()

        for dummy in range(1000):
            self.wfile.write(b'0' * 10000)

    def infinite(self):
        self.send_response(200)
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        while True:
            self.wfile.write(b'2710\r\n')
            self.wfile.write(b'0' * 10000)
            self.wfile.write(b'\r\n')

    def gzip_http_1_0(self):
        self.send_response(200)
        self.send_header('Content-encoding', 'gzip')
        self.end_headers()

        self.wfile.write(self.gzip_sample())

        self.close_connection = True

    def zlib_http_1_0(self):
        self.send_response(200)
        self.send_header('Content-encoding', 'deflate')
        self.end_headers()

        self.wfile.write(self.zlib_sample())

        self.close_connection = True

    def raw_deflate_http_1_0(self):
        self.send_response(200)
        self.send_header('Content-encoding', 'deflate')
        self.end_headers()

        self.wfile.write(self.raw_deflate_sample())

        self.close_connection = True

    def gzip_http_1_1(self):
        data = self.gzip_sample()

        self.send_response(200)
        self.send_header('Content-encoding', 'gzip')
        self.send_header('Content-length', str(len(data)))
        self.end_headers()

        self.wfile.write(data)

    def gzip_chunked(self):
        data_file = io.BytesIO(self.gzip_sample())

        self.send_response(200)
        self.send_header('Content-encoding', 'gzip')
        self.send_header('Transfer-encoding', 'chunked')
        self.end_headers()

        while True:
            data = data_file.read(100)

            assert len(data) <= 100

            if not data:
                break

            self.wfile.write('{0:x}'.format(len(data)).encode('ascii'))
            self.wfile.write(b'\r\n')
            self.wfile.write(data)
            self.wfile.write(b'\r\n')

        self.wfile.write(b'0\r\n\r\n')

        self.close_connection = True

    def zlib_chunked(self):
        data_file = io.BytesIO(self.zlib_sample())

        self.send_response(200)
        self.send_header('Content-encoding', 'deflate')
        self.send_header('Transfer-encoding', 'chunked')
        self.end_headers()

        while True:
            data = data_file.read(100)

            assert len(data) <= 100

            if not data:
                break

            self.wfile.write('{0:x}'.format(len(data)).encode('ascii'))
            self.wfile.write(b'\r\n')
            self.wfile.write(data)
            self.wfile.write(b'\r\n')

        self.wfile.write(b'0\r\n\r\n')

        self.close_connection = True

    def raw_deflate_chunked(self):
        data_file = io.BytesIO(self.raw_deflate_sample())

        self.send_response(200)
        self.send_header('Content-encoding', 'deflate')
        self.send_header('Transfer-encoding', 'chunked')
        self.end_headers()

        while True:
            data = data_file.read(100)

            assert len(data) <= 100

            if not data:
                break

            self.wfile.write('{0:x}'.format(len(data)).encode('ascii'))
            self.wfile.write(b'\r\n')
            self.wfile.write(data)
            self.wfile.write(b'\r\n')

        self.wfile.write(b'0\r\n\r\n')

        self.close_connection = True

    def gzip_corrupt_short(self):
        data = self.gzip_sample()
        data = data[:len(data) // 2]

        self.send_response(200)
        self.send_header('Content-encoding', 'gzip')
        self.send_header('Content-length', str(len(data)))
        self.end_headers()

        self.wfile.write(data)

    def gzip_corrupt_footer(self):
        data = base64.b16decode(
            b'1f8b0800f95a11530003030000000000deadbeef',
            casefold=True
        )

        self.send_response(200)
        self.send_header('Content-encoding', 'gzip')
        self.send_header('Content-length', str(len(data)))
        self.end_headers()

        self.wfile.write(data)

    def gzip_sample(self):
        content_file = io.BytesIO()
        with GzipFile(fileobj=content_file, mode='wb') as gzip_file:
            path = os.path.join(
                os.path.dirname(__file__), 'samples', 'xkcd_1.html')
            with open(path, 'rb') as in_file:
                gzip_file.write(in_file.read())

        return content_file.getvalue()

    def zlib_sample(self):
        path = os.path.join(
            os.path.dirname(__file__), 'samples', 'xkcd_1.html')

        with open(path, 'rb') as in_file:
            return zlib.compress(in_file.read())

    def raw_deflate_sample(self):
        return self.zlib_sample()[2:-4]

    def bad_cookie(self):
        self.send_response(200)
        self.send_header(
            'Set-cookie',
            '\x00?#?+:%ff=hope you have cookies enabled!; expires=Dog'
        )
        self.send_header('Set-cookie', 'COOKIES')
        self.send_header('Set-cookie', 'test=valid')
        self.send_header('Set-cookie', 'bad=date?; Expires=Sit, 28 Dec 2024 01:59:61 GMT')
        self.send_header('Set-cookie', 'bad=date?; Expires=Sat, 28 Dec-2024 01:59:61 GMT')
        self.send_header('Set-cookie', '; Expires=Thu, 01 Jan 1970 00:00:10 GMT')
        self.send_header('Content-length', '0')
        self.end_headers()

    def long_cookie(self):
        self.send_response(200)
        self.send_header(
            'Set-cookie',
            'a={0}'.format('b' * 5000)
        )
        self.send_header('Content-length', '0')
        self.end_headers()

    def header_early_close(self):
        # http://stackoverflow.com/a/6440364/1524507
        l_onoff = 1
        l_linger = 0
        self.connection.setsockopt(
            socket.SOL_SOCKET, socket.SO_LINGER,
            struct.pack(b'ii', l_onoff, l_linger)
        )
        _logger.debug('Bad socket reset set.')

        self.wfile.write(b'HTTP/1.0 200 OK')
        self.close_connection = True

    def no_content(self):
        self.send_response(204)
        self.end_headers()

    def many_links(self):
        self.send_response(200)
        self.end_headers()

        self.wfile.write(b'<html><body>')

        for dummy in range(10000):
            self.wfile.write(b'<a href="/many_links?')
            self.wfile.write(str(random.randint(0, 1000000)).encode('ascii'))
            self.wfile.write(b'">hi</a>')
            self.wfile.write(b'<img src="/?')
            self.wfile.write(str(random.randint(0, 1000000)).encode('ascii'))
            self.wfile.write(b'"><br>')

        self.wfile.write(b'</html>')

        self.close_connection = True

    def non_http_redirect(self):
        self.send_response(302)
        self.send_header('Location', 'mailto:user@example.com')
        self.send_header('Content-Length', 0)
        self.end_headers()

    def bad_redirect(self):
        self.send_response(303)
        self.send_header(
            'Location',
            'http://Yes, some websites do this - '
            'I have no idea why - Please do not ask - '
            'Perhaps a wolf programmed the site'
        )
        self.send_header('Content-Length', 0)
        self.end_headers()
        
    def bad_redirect_ipv6(self):
        self.send_response(303)
        self.send_header(
            'Location',
            'http://]/'
        )
        self.send_header('Content-Length', 0)
        self.end_headers()

    def utf8_then_binary(self):
        self.send_response(200)

        if self.path.endswith('js'):
            self.send_header(
                'Content-Type', 'application/javascript; charset=utf8')
        elif self.path.endswith('xml'):
            self.send_header(
                'Content-Type', 'text/xml; charset=utf8')
        elif self.path.endswith('css'):
            self.send_header(
                'Content-Type', 'text/css; charset=utf8')
        else:
            self.send_header('Content-Type', 'text/html; charset=utf8')

        self.end_headers()

        data = (
            '᚛᚛ᚉᚑᚅᚔᚉᚉᚔᚋ ᚔᚈᚔ ᚍᚂᚐᚅᚑ ᚅᚔᚋᚌᚓᚅᚐ᚜'
            'Je peux manger du verre, ça ne me fait pas mal.'
            "Dw i'n gallu bwyta gwydr, 'dyw e ddim yn gwneud dolur i mi."
        ).encode('utf8')

        for dummy in range(8000):
            self.wfile.write(data)

        self.wfile.write(b'\xfe')

        for dummy in range(10):
            self.wfile.write(data)

        self.close_connection = True

    def false_gzip(self):
        self.send_response(200)
        self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Length', 100)
        self.end_headers()

        self.wfile.write(b'a' * 100)

    def status_line_only(self):
        self.wfile.write(b'HTTP/1.1 200 OK\r\n\r\n')
        self.wfile.write(b'Hey')
        self.close_connection = True

    def newline_line_only(self):
        self.wfile.write(b'\r\n\r\n')
        self.wfile.write(b'Hey')
        self.close_connection = True

    def many_headers(self):
        self.wfile.write(b'HTTP/1.1 200 I Heard You Like Headers\r\n')
        for num in range(10000):
            self.wfile.write('Hey-{0}:'.format(num).encode('ascii'))
            self.wfile.write(b'hey' * 1000 + b'\r\n')

        self.wfile.write(b'\r\n')
        self.close_connection = True


class ConcurrentHTTPServer(socketserver.ThreadingMixIn,
                           http.server.HTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        http.server.HTTPServer.__init__(self, *args, **kwargs)
#         self.daemon_threads = True


class Server(threading.Thread):
    def __init__(self, port=0, enable_ssl=False):
        threading.Thread.__init__(self)
        self.daemon = True
        self._port = port
        self._server = ConcurrentHTTPServer(
            ('localhost', self._port), Handler)
        self._port = self._server.server_address[1]

        if enable_ssl:
            self._server.socket = ssl.wrap_socket(
                self._server.socket,
                certfile=os.path.join(os.path.dirname(__file__), 'test.pem'),
                server_side=True)

        _logger.debug(
            'Server bound to {0}'.format(self._server.server_address))
        self.started_event = threading.Event()

    def run(self):
        self.started_event.set()
        _logger.debug('Server running.')
        self._server.serve_forever()

    def stop(self):
        _logger.debug('Server stopping...')
        self._server.shutdown()
        _logger.debug('Server stopped.')

    @property
    def port(self):
        return self._port


class BadAppTestCase(AsyncTestCase, TornadoAsyncTestCase):
    def get_new_ioloop(self):
        tornado.ioloop.IOLoop.configure(
            'wpull.testing.async.TornadoAsyncIOLoop',
            event_loop=self.event_loop)
        ioloop = tornado.ioloop.IOLoop()
        return ioloop

    def setUp(self):
        AsyncTestCase.setUp(self)
        TornadoAsyncTestCase.setUp(self)
        self.http_server = Server(enable_ssl=self.get_protocol() == 'https')
        self.http_server.start()
        self.http_server.started_event.wait(timeout=5.0)
        self._port = self.http_server.port

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
        self.http_server.join(timeout=5)
        AsyncTestCase.tearDown(self)
        TornadoAsyncTestCase.tearDown(self)


class SSLBadAppTestCase(BadAppTestCase):
    def get_protocol(self):
        return 'https'

if __name__ == '__main__':
    server = Server(8888)
    server.start()
    server.join()
