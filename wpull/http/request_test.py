# encoding=utf-8

import unittest

from wpull.errors import ProtocolError
from wpull.http.request import Request, Response


class TestRequest(unittest.TestCase):
    def test_request(self):
        request = Request('http://example.com/robots.txt')
        request.prepare_for_send()
        self.assertEqual(
            (b'GET /robots.txt HTTP/1.1\r\n'
             b'Host: example.com\r\n'
             b'\r\n'),
            request.to_bytes()
        )

    def test_request_port(self):
        request = Request('https://example.com:4567/robots.txt')
        request.prepare_for_send()
        self.assertEqual(
            (b'GET /robots.txt HTTP/1.1\r\n'
             b'Host: example.com:4567\r\n'
             b'\r\n'),
            request.to_bytes()
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
