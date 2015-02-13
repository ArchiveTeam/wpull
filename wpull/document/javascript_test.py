import unittest
import io

from wpull.document.base import VeryFalse
from wpull.document.javascript import JavaScriptReader
from wpull.http.request import Response


class TestJavaScript(unittest.TestCase):
    def test_js_detect(self):
        self.assertTrue(JavaScriptReader.is_file(
            io.BytesIO('var a = 1;'.encode('utf-16le'))
        ))
        self.assertTrue(JavaScriptReader.is_file(
            io.BytesIO('setTimeout('.encode('utf-16le'))
        ))
        self.assertFalse(JavaScriptReader.is_file(
            io.BytesIO('hello world!'.encode('utf-16le'))
        ))
        self.assertFalse(JavaScriptReader.is_file(
            io.BytesIO(b'<html><body>hello')
        ))
        self.assertTrue(JavaScriptReader.is_file(
            io.BytesIO(b'<html><body>hello')
        ) is VeryFalse)

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'application/javascript'
        self.assertTrue(JavaScriptReader.is_response(response))

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'image/png'
        self.assertFalse(JavaScriptReader.is_response(response))
