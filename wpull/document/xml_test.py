import io
import unittest

from wpull.document.xml import XMLDetector
from wpull.http.request import Request, Response
from wpull.url import URLInfo


class TestXML(unittest.TestCase):
    def test_xml_detect(self):
        self.assertTrue(XMLDetector.is_file(
            io.BytesIO('<?xml version='.encode('utf-16le'))
        ))
        self.assertFalse(XMLDetector.is_file(
            io.BytesIO('<!DOCTYPE html><html><body>'.encode('utf-16le'))
        ))
        self.assertFalse(XMLDetector.is_file(
            io.BytesIO(b'<html><body>hello')
        ))
        self.assertTrue(XMLDetector.is_file(
            io.BytesIO(b'<?xml version')
        ))
        self.assertTrue(
            XMLDetector.is_url(URLInfo.parse('example.com/index.xml'))
        )
        self.assertFalse(
            XMLDetector.is_url(URLInfo.parse('example.com/image.jpg'))
        )
        self.assertTrue(
            XMLDetector.is_request(Request('example.com/index.xml'))
        )
        self.assertFalse(
            XMLDetector.is_request(Request('example.com/image.jpg'))
        )

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'text/xml'
        self.assertTrue(XMLDetector.is_response(response))

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'application/xml'
        self.assertTrue(XMLDetector.is_response(response))

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'image/png'
        self.assertFalse(XMLDetector.is_response(response))
