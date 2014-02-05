# encoding=utf-8
import sys

from wpull.backport.testing import unittest
from wpull.http import Request, Response
from wpull.wrapper import convert_http_request, HTTPResponseInfoWrapper


class TestWrapper(unittest.TestCase):
    def test_http_request(self):
        request = Request.new('http://example.com')
        request.fields['hello'] = 'world'
        new_request = convert_http_request(request)

        if sys.version_info[0] == 2:
            self.assertEqual('example.com', new_request.get_host())
        else:
            self.assertEqual('example.com', new_request.host)

        self.assertEqual('world', new_request.get_header('Hello'))

    def test_http_response(self):
        response = Response('HTTP/1.0', 200, 'OK')
        response.fields['hello'] = 'world'

        new_response = HTTPResponseInfoWrapper(response)
        info = new_response.info()

        self.assertEqual('world', info.get('hello'))
