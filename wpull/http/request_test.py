# encoding=utf-8

import copy
import unittest
from wpull.body import Body

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

    def test_request_parse(self):
        request = Request()
        request.parse(b'GET /robots.txt HTTP/1.1\r\n')
        request.parse(b'Host: example.com\r\n')
        request.parse('Accept: éxample\r\n'.encode('utf_8'))
        request.parse(b'\r\n')

        self.assertEqual('http://example.com/robots.txt', request.url)
        self.assertEqual('example.com', request.fields['host'])
        self.assertEqual('éxample'.encode('utf-8').decode('latin-1'),
                         request.fields['accept'])

        request = Request()
        request.parse(b'GET https://example.com/robots.txt HTTP/1.1\r\n')
        request.parse(b'Host: example.com\r\n')
        request.parse(b'Accept: \xffexample\r\n')
        request.parse(b'\r\n')

        self.assertEqual('https://example.com/robots.txt', request.url)
        self.assertEqual('example.com', request.fields['host'])
        self.assertEqual('\xffexample', request.fields['accept'])

    def test_response(self):
        response = Response(200, 'OK')
        response.fields['Cake'] = 'dolphin'

        self.assertEqual(
            (b'HTTP/1.1 200 OK\r\n'
             b'Cake: dolphin\r\n'
             b'\r\n'),
            response.to_bytes()
        )

    def test_response_parse(self):
        response = Response()
        response.parse(b'HTTP/1.0 200 OK\r\n')
        response.parse('Cake: dolphın\r\n'.encode('utf-8'))
        response.parse(b'\r\n')

        self.assertEqual(200, response.status_code)
        self.assertEqual('OK', response.reason)
        self.assertEqual('dolphın'.encode('utf-8').decode('latin-1'),
                         response.fields['Cake'])

        response = Response()
        response.parse(b'HTTP/1.0 200 OK\r\n')
        response.parse(b'Cake: \xffdolphin\r\n')
        response.parse(b'\r\n')

        self.assertEqual(200, response.status_code)
        self.assertEqual('OK', response.reason)
        self.assertEqual('\xffdolphin', response.fields['Cake'])

    def test_response_empty_reason_line(self):
        response = Response()
        response.parse(b'HTTP/1.0 200\r\n')
        response.parse(b'Cake: dolphin\r\n')
        response.parse(b'\r\n')

        self.assertEqual(200, response.status_code)
        self.assertEqual('', response.reason)
        self.assertEqual('dolphin', response.fields['Cake'])

    def test_response_status_codes(self):
        response = Response()
        response.parse(b'HTTP/1.0 0\r\n')
        response.parse(b'\r\n')

        self.assertEqual(0, response.status_code)

        response = Response()
        response.parse(b'HTTP/1.0 999\r\n')
        response.parse(b'\r\n')

        self.assertEqual(999, response.status_code)

        response = Response(0, '')
        self.assertEqual(0, response.status_code)

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

    def test_copy(self):
        request = Request('http://twitcharchivestheinternet.invalid/')

        # Cheeck for no crash
        request.copy()

    def test_to_dict(self):
        request = Request('https://foofle.com')
        request_dict = request.to_dict()

        self.assertEqual('https://foofle.com', request_dict['url'])
        self.assertEqual('https', request_dict['url_info']['scheme'])
        self.assertEqual('GET', request_dict['method'])
        self.assertEqual('http', request_dict['protocol'])

        response = Response(status_code=200, reason='OK', request=request)
        response_dict = response.to_dict()

        self.assertEqual(
            'https://foofle.com',
            response_dict['request']['url']
        )
        self.assertEqual('http', response_dict['protocol'])
        self.assertEqual(200, response_dict['status_code'])
        self.assertEqual(200, response_dict['response_code'])
        self.assertEqual('OK', response_dict['reason'])
        self.assertEqual('OK', response_dict['response_message'])

    def test_to_dict_body(self):
        request = Request()
        request.body = Body()
        request_dict = request.to_dict()

        self.assertTrue(request_dict['body'])
        request.body.close()

        request = Request()
        request.body = NotImplemented
        request_dict = request.to_dict()

        self.assertFalse(request_dict['body'])

        response = Response()
        response.body = Body()
        response_dict = response.to_dict()

        self.assertTrue(response_dict['body'])
        response.body.close()

        response = Response()
        response.body = NotImplemented
        response_dict = response.to_dict()

        self.assertFalse(response_dict['body'])
