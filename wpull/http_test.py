# encoding=utf-8
import functools
import os.path
import tornado.testing
import tornado.web

from wpull.backport.testing import unittest
from wpull.errors import ConnectionRefused, SSLVerficationError
from wpull.http import (Request, Connection, NetworkError, ProtocolError, Client,
    ConnectionPool, parse_charset, Response, HostConnectionPool)
from wpull.recorder import DebugPrintRecorder
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestConnection(BadAppTestCase):
    def setUp(self):
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_no_such_host(self):
        connection = Connection('wpull-no-exist.invalid', 80)
        try:
            yield connection.fetch(
                Request.new('http://wpull-no-exist.invalid'))
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_refused(self):
        connection = Connection('localhost', 1)
        try:
            yield connection.fetch(
                Request.new('http://localhost:1/'))
        except ConnectionRefused:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_timeout(self):
        connection = Connection('1.0.0.0', 1, connect_timeout=0.1)
        try:
            yield connection.fetch(
                Request.new('http://1.0.0.0:1/'))
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_reuse(self):
        connection = Connection('localhost', self._port)
        request = Request.new(self.get_url('/'))
        request.version = 'HTTP/1.0'
        response = yield connection.fetch(request)
        self.assertEqual(200, response.status_code)
        response = yield connection.fetch(request)
        self.assertEqual(200, response.status_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_read_timeout(self):
        connection = Connection('localhost', self._port, read_timeout=0.1)
        request = Request.new(self.get_url('/sleep_long'))
        try:
            yield connection.fetch(request)
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        response = yield self.fetch('/')
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'hello world!', response.body.content)
        self.assertTrue(response.url_info)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_content_length(self):
        response = yield self.fetch('/content_length')
        self.assertEqual(200, response.status_code)
        self.assertEqual('100', response.fields['Content-Length'])
        self.assertEqual(b'a' * 100, response.body.content)
        self.assertEqual(100, response.body.content_size)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_chunked(self):
        response = yield self.fetch('/chunked')
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', response.body.content)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_chunked_trailer(self):
        response = yield self.fetch('/chunked_trailer')
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual('dolphin', response.fields['Animal'])
        self.assertEqual(b'hello world!', response.body.content)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_malformed_chunked(self):
        try:
            yield self.fetch('/malformed_chunked')
        except ProtocolError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_buffer_overflow(self):
        connection = Connection('localhost', self._port,
            connect_timeout=2.0, read_timeout=5.0, buffer_size=1000)
        request = Request.new(self.get_url('/buffer_overflow'))
        try:
            yield connection.fetch(request)
        except (ProtocolError, NetworkError):
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_chunk_size(self):
        try:
            yield self.fetch('/bad_chunk_size')
        except ProtocolError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_content_length_and_chunked(self):
        response = yield self.fetch('/content_length_and_chunked')
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', response.body.content)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_header_delminators(self):
        response = yield self.fetch('/bad_header_deliminators')
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'hi\n', response.body.content)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_utf8_header(self):
        response = yield self.fetch('/utf8_header')
        self.assertEqual(200, response.status_code)
        self.assertEqual('🐱', response.fields['whoa'])

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_short_close(self):
        try:
            yield self.fetch('/short_close')
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_header_early_close(self):
        try:
            yield self.fetch('/header_early_close')
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_unclean_8bit_header(self):
        yield self.fetch('/unclean_8bit_header')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_no_colon_header(self):
        yield self.fetch('/no_colon_header')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_malformed_content_length(self):
        yield self.fetch('/malformed_content_length')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_negative_content_length(self):
        yield self.fetch('/negative_content_length')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_gzip_encoding(self):
        filename = os.path.join(
            os.path.dirname(__file__), 'testing', 'samples', 'xkcd_1.html')

        with open(filename, 'rb') as in_file:
            test_data = in_file.read()

        paths = ['/gzip_http_1_0', '/gzip_http_1_1', '/gzip_chunked']
        for path in paths:
            print('Fetching', path)
            response = yield self.fetch(path)

            self.assertEqual(len(test_data), len(response.body.content))
            self.assertEqual(test_data, response.body.content)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        yield self.fetch('/no_content')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_head_no_content(self):
        yield self.connection.fetch(
            Request.new(self.get_url('/no_content'), method='HEAD'),
            DebugPrintRecorder()
        )


class TestClient(BadAppTestCase):
    def setUp(self):
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_min(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)

        for dummy in range(2):
            response = yield client.fetch(
                Request.new(self.get_url('/sleep_short')))
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(1, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_max(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/sleep_short'))) for dummy in range(6)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(6, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_over_max(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/sleep_short'))) for dummy in range(12)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(6, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_clean(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/'))) for dummy in range(12)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)

        connection_pool.clean()

        self.assertEqual(0, len(connection_pool))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_throw(self):
        client = Client()

        try:
            yield client.fetch(Request.new('http://wpull-no-exist.invalid'))
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_recovery(self):
        connection_factory = functools.partial(Connection, read_timeout=0.2)
        host_connection_pool_factory = functools.partial(
            HostConnectionPool, connection_factory=connection_factory)
        connection_pool = ConnectionPool(host_connection_pool_factory)
        client = Client(connection_pool)

        for dummy in range(7):
            try:
                yield client.fetch(
                    Request.new(self.get_url('/header_early_close')),
                    recorder=DebugPrintRecorder()
                )
            except NetworkError:
                pass
            else:
                self.fail()

        for dummy in range(7):
            response = yield client.fetch(Request.new(self.get_url('/')))
            self.assertEqual(200, response.status_code)


class TestHTTP(unittest.TestCase):
    def test_request(self):
        request = Request.new('http://example.com/robots.txt')
        self.assertEqual(
            (b'GET /robots.txt HTTP/1.1\r\n'
            b'Host: example.com\r\n'
            b'\r\n'),
            request.header()
        )

    def test_parse_charset(self):
        self.assertEqual(
            None,
            parse_charset('text/plain')
        )
        self.assertEqual(
            None,
            parse_charset('text/plain; charset=')
        )
        self.assertEqual(
            'utf_8',
            parse_charset('text/plain; charset=utf_8')
        )
        self.assertEqual(
            'UTF-8',
            parse_charset('text/plain; charset="UTF-8"')
        )
        self.assertEqual(
            'Utf8',
            parse_charset("text/plain; charset='Utf8'")
        )
        self.assertEqual(
            'UTF-8',
            parse_charset('text/plain; CHARSET="UTF-8"')
        )

    def test_parse_status_line(self):
        version, code, msg = Response.parse_status_line(b'HTTP/1.0 200 OK')
        self.assertEqual('HTTP/1.0', version)
        self.assertEqual(200, code)
        self.assertEqual('OK', msg)

        version, code, msg = Response.parse_status_line(
            b'HTTP/1.0 404 Not Found')
        self.assertEqual('HTTP/1.0', version)
        self.assertEqual(404, code)
        self.assertEqual('Not Found', msg)

        version, code, msg = Response.parse_status_line(b'HTTP/1.1  200   OK')
        self.assertEqual('HTTP/1.1', version)
        self.assertEqual(200, code)
        self.assertEqual('OK', msg)

        version, code, msg = Response.parse_status_line(b'HTTP/1.1  200')
        self.assertEqual('HTTP/1.1', version)
        self.assertEqual(200, code)
        self.assertEqual('', msg)

        version, code, msg = Response.parse_status_line(b'HTTP/1.1  200  ')
        self.assertEqual('HTTP/1.1', version)
        self.assertEqual(200, code)
        self.assertEqual('', msg)

        version, code, msg = Response.parse_status_line(
            'HTTP/1.1 200 ððð'.encode('latin-1'))
        self.assertEqual('HTTP/1.1', version)
        self.assertEqual(200, code)
        self.assertEqual('ððð', msg)

        self.assertRaises(
            ProtocolError,
            Response.parse_status_line, b'HTTP/1.0'
        )
        self.assertRaises(
            ProtocolError,
            Response.parse_status_line, b'HTTP/2.0'
        )

        version, code, msg = Response.parse_status_line(
            b'HTTP/1.0 404 N\x99t \x0eounz\r\n')
        self.assertEqual('HTTP/1.0', version)
        self.assertEqual(404, code)
        self.assertEqual(b'N\x99t \x0eounz'.decode('latin-1'), msg)


class TestSSL(tornado.testing.AsyncHTTPSTestCase):
    def get_app(self):
        return tornado.web.Application()

    def test_ssl_fail(self):
        connection = Connection('localhost', self.get_http_port())
        try:
            yield connection.fetch(Request.new(self.get_url('/')))
        except SSLVerficationError:
            pass
        else:
            self.fail()
