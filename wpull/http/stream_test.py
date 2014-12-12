# encoding=utf-8
import io
import logging
import os.path
import socket
import ssl
import sys
import unittest

import tornado.netutil
from trollius import From, Return
import trollius

from wpull.connection import Connection, SSLConnection
from wpull.errors import NetworkError, ConnectionRefused, ProtocolError, \
    NetworkTimedOut, SSLVerificationError
from wpull.http.request import Request
from wpull.http.stream import Stream
import wpull.testing.async
from wpull.testing.badapp import BadAppTestCase, SSLBadAppTestCase


DEFAULT_TIMEOUT = 30

_logger = logging.getLogger(__name__)


class StreamTestsMixin(object):
    def get_ssl_default(self):
        return None

    def new_stream(self, host=None, port=None, ssl=None,
                   connection_kwargs=None, **kwargs):
        if connection_kwargs is None:
            connection_kwargs = {}

        if ssl is None:
            ssl = self.get_ssl_default()

        if ssl:
            connection = SSLConnection(
                (host or '127.0.0.1', port or self._port), **connection_kwargs)
        else:
            connection = Connection(
                (host or '127.0.0.1', port or self._port), **connection_kwargs)

        stream = Stream(connection, **kwargs)

        non_local_dict = {'count': 0}

        def debug_handler(data_type, data):
            if non_local_dict['count'] < 50:
                _logger.debug('%s %s', data_type, data[:100])

                non_local_dict['count'] += 1

                if non_local_dict['count'] == 50:
                    _logger.debug('Discarding for performance.')

        stream.data_observer.add(debug_handler)

        return stream

    @trollius.coroutine
    def fetch(self, stream, request):
        yield From(stream.write_request(request))
        response = yield From(stream.read_response())
        content = io.BytesIO()
        yield From(stream.read_body(request, response, content))
        raise Return(response, content.getvalue())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_such_host(self):
        stream = self.new_stream('wpull-no-exist.invalid', 80)
        try:
            yield From(
                self.fetch(stream, Request('http://wpull-no-exist.invalid')))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_refused(self):
        stream = self.new_stream('127.0.0.1', 1)
        try:
            yield From(self.fetch(stream, Request('http://localhost:1/')))
        except ConnectionRefused:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_timeout(self):
        stream = self.new_stream('1.0.0.0', 1,
                                 connection_kwargs=dict(connect_timeout=0.1))

        try:
            yield From(self.fetch(stream, Request('http://1.0.0.0:1/')))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_reuse(self):
        stream = self.new_stream()
        request = Request(self.get_url('/'))
        request.version = 'HTTP/1.0'
        response, dummy = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        response, dummy = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_reuse_with_http_close(self):
        stream = self.new_stream()

        for dummy in range(5):
            request = Request(self.get_url('/content_length_with_close'))
            response, content = yield From(self.fetch(stream, request))
            self.assertEqual(200, response.status_code)
            self.assertEqual('100', response.fields['Content-Length'])
            self.assertEqual(100, len(content))
            self.assertEqual(b'a' * 100, content)

    @unittest.skip("This case is too difficult to solve.")
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_reuse_without_http_close(self):
        stream = self.new_stream()

        for dummy in range(5):
            request = Request('/content_length_without_close')
            response, content = yield From(self.fetch(stream, request))
            self.assertEqual(200, response.status_code)
            self.assertEqual('100', response.fields['Content-Length'])
            self.assertEqual(100, len(content))
            self.assertEqual(b'a' * 100, content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_read_timeout(self):
        stream = self.new_stream(connection_kwargs=dict(timeout=0.1))
        request = Request(self.get_url('/sleep_long'))
        try:
            yield From(self.fetch(stream, request))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        stream = self.new_stream()
        request = Request(self.get_url('/'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'hello world!', content)
#         self.assertTrue(response.url_info)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_content_length(self):
        stream = self.new_stream()
        request = Request(self.get_url('/content_length'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('100', response.fields['Content-Length'])
        self.assertEqual(b'a' * 100, content)
        self.assertEqual(100, len(content))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_chunked(self):
        stream = self.new_stream()
        request = Request(self.get_url('/chunked'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_chunked_trailer(self):
        stream = self.new_stream()
        request = Request(self.get_url('/chunked_trailer'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual('dolphin', response.fields['Animal'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_chunked_trailer_2(self):
        stream = self.new_stream()
        request = Request(self.get_url('/chunked_trailer_2'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual('dolphin', response.fields['Animal'])
        self.assertEqual('delicious', response.fields['Cake'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_malformed_chunked(self):
        stream = self.new_stream()
        request = Request(self.get_url('/malformed_chunked'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_non_standard_delim_chunked(self):
        stream = self.new_stream()
        request = Request(self.get_url('/chunked_non_standard_delim'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_chunked_with_extension(self):
        stream = self.new_stream()
        request = Request(self.get_url('/chunked_with_extension'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_buffer_overflow(self):
        stream = self.new_stream()
        request = Request(self.get_url('/buffer_overflow'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_buffer_overflow_header(self):
        stream = self.new_stream()
        request = Request(self.get_url('/buffer_overflow_header'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_chunk_size(self):
        stream = self.new_stream()
        request = Request(self.get_url('/bad_chunk_size'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_content_length_and_chunked(self):
        stream = self.new_stream()
        request = Request(self.get_url('/content_length_and_chunked'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('chunked', response.fields['Transfer-Encoding'])
        self.assertEqual(b'hello world!', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_header_delminators(self):
        stream = self.new_stream()
        request = Request(self.get_url('/bad_header_deliminators'))
        response, content = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual(b'hi\n', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_utf8_header(self):
        stream = self.new_stream()
        request = Request(self.get_url('/utf8_header'))
        response, dummy = yield From(self.fetch(stream, request))
        self.assertEqual(200, response.status_code)
        self.assertEqual('🐱'.encode('utf-8').decode('latin-1'),
                         response.fields['whoa'])

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_short_close(self):
        stream = self.new_stream()
        request = Request(self.get_url('/short_close'))
        try:
            yield From(self.fetch(stream, request))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

        request = Request(self.get_url('/'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_header_early_close(self):
        stream = self.new_stream()
        request = Request(self.get_url('/header_early_close'))
        try:
            yield From(self.fetch(stream, request))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

        request = Request(self.get_url('/'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_unclean_8bit_header(self):
        stream = self.new_stream()
        request = Request(self.get_url('/unclean_8bit_header'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_colon_header(self):
        stream = self.new_stream()
        request = Request(self.get_url('/no_colon_header'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_malformed_content_length(self):
        stream = self.new_stream()
        request = Request(self.get_url('/malformed_content_length'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_negative_content_length(self):
        stream = self.new_stream()
        request = Request(self.get_url('/negative_content_length'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_gzip_encoding(self):
        filename = os.path.join(
            os.path.dirname(__file__),
            '..', 'testing', 'samples', 'xkcd_1.html'
        )

        with open(filename, 'rb') as in_file:
            test_data = in_file.read()

        paths = ['/gzip_http_1_0', '/gzip_http_1_1', '/gzip_chunked']
        for path in paths:
            print('Fetching', path)
            stream = self.new_stream()
            request = Request(self.get_url(path))
            response, content = yield From(self.fetch(stream, request))

            self.assertEqual(len(test_data), len(content))
            self.assertEqual(test_data, content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_zlib_encoding(self):
        filename = os.path.join(
            os.path.dirname(__file__),
            '..', 'testing', 'samples', 'xkcd_1.html'
        )

        with open(filename, 'rb') as in_file:
            test_data = in_file.read()

        paths = [
            '/zlib_http_1_0', '/raw_deflate_http_1_0',
            '/zlib_chunked', '/raw_deflate_chunked',
        ]
        for path in paths:
            print('Fetching', path)
            stream = self.new_stream()
            request = Request(self.get_url(path))
            response, content = yield From(self.fetch(stream, request))

            self.assertEqual(len(test_data), len(content))
            self.assertEqual(test_data, content)

    @unittest.skip('zlib seems to not error on short content')
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_gzip_corrupt_short(self):
        stream = self.new_stream()
        request = Request(self.get_url('/gzip_corrupt_short'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_gzip_corrupt_footer(self):
        stream = self.new_stream()
        request = Request(self.get_url('/gzip_corrupt_footer'))
        try:
            yield From(self.fetch(stream, request))
        except ProtocolError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        stream = self.new_stream()
        request = Request(self.get_url('/no_content'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_head_no_content(self):
        stream = self.new_stream()
        request = Request(self.get_url('/no_content'), method='HEAD')
        yield From(self.fetch(stream, request))

    # XXX: why is this slow on travis
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT * 4)
    def test_big(self):
        stream = self.new_stream()
        request = Request(self.get_url('/big'))
        response, content = yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_underrun(self):
        stream = self.new_stream(
            connection_kwargs=dict(connect_timeout=2.0, timeout=1.0))
        request = Request(self.get_url('/underrun'))

        for counter in range(3):
            print(counter)
            try:
                yield From(self.fetch(stream, request))
            except NetworkTimedOut:
                pass
            else:
                self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_overrun(self):
        stream = self.new_stream()
        request = Request(self.get_url('/overrun'))

        for dummy in range(3):
            response, content = yield From(self.fetch(stream, request))

            self.assertEqual(b'a' * 100, content)

        request = Request(self.get_url('/'))
        yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_ignore_length(self):
        stream = self.new_stream('127.0.0.1', self._port,
                                 keep_alive=False, ignore_length=True)
        request = Request(self.get_url('/underrun'))

        response, content = yield From(self.fetch(stream, request))

        self.assertEqual(50, len(content))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_false_gzip(self):
        stream = self.new_stream('127.0.0.1', self._port)
        request = Request(self.get_url('/false_gzip'))
        response, content = yield From(self.fetch(stream, request))

        self.assertEqual('gzip', response.fields['Content-Encoding'])
        self.assertEqual(b'a' * 100, content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_status_line_only(self):
        stream = self.new_stream('127.0.0.1', self._port)
        request = Request(self.get_url('/status_line_only'))
        response, content = yield From(self.fetch(stream, request))

        self.assertEqual(200, response.status_code)
        self.assertEqual(b'Hey', content)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_newline_line_only(self):
        stream = self.new_stream('127.0.0.1', self._port)
        request = Request(self.get_url('/newline_line_only'))

        with self.assertRaises(ProtocolError):
            yield From(self.fetch(stream, request))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_many_headers(self):
        stream = self.new_stream('127.0.0.1', self._port)
        request = Request(self.get_url('/many_headers'))

        with self.assertRaises(ProtocolError):
            yield From(self.fetch(stream, request))


class TestStream(BadAppTestCase, StreamTestsMixin):
    pass


class TestSSLStream(SSLBadAppTestCase, StreamTestsMixin):
    def get_ssl_default(self):
        return True

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_ssl_fail(self):
        ssl_options = dict(
            cert_reqs=ssl.CERT_REQUIRED,
            ca_certs=os.path.join(os.path.dirname(__file__),
                                  '..', 'cert', 'ca-bundle.pem'),
        )
        ssl_context = tornado.netutil.ssl_options_to_context(ssl_options)
        stream = self.new_stream(
            ssl=True, connection_kwargs=dict(ssl_context=ssl_context))
        request = Request(self.get_url('/'))

        try:
            yield From(self.fetch(stream, request))
        except SSLVerificationError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_ssl_no_check(self):
        stream = self.new_stream(ssl=True)
        request = Request(self.get_url('/'))

        yield From(self.fetch(stream, request))
