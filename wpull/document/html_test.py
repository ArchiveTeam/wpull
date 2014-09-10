import io
import unittest

from wpull.document.base_test import CODEC_NAMES
from wpull.document.html import HTMLReader
from wpull.document.htmlparse.lxml import HTMLParser as LxmlHTMLParser
from wpull.http.request import Request, Response
from wpull.url import URLInfo


class Mixin(object):
    def get_html_parser(self):
        raise NotImplementedError()

    def test_html_detect(self):
        self.assertTrue(HTMLReader.is_file(
            io.BytesIO('<html><body>hi</body></html>'.encode('utf-16le'))
        ))
        self.assertFalse(HTMLReader.is_file(
            io.BytesIO('hello world!'.encode('utf-16le'))
        ))
        self.assertTrue(HTMLReader.is_file(
            io.BytesIO(b'<title>hello</title>hi')
        ))
        self.assertTrue(HTMLReader.is_file(
            io.BytesIO(b'<html><body>hello')
        ))
        self.assertTrue(HTMLReader.is_file(
            io.BytesIO(
                b'The document has moved <a href="somewhere.html">here</a>'
            )
        ))
        self.assertTrue(
            HTMLReader.is_url(URLInfo.parse('example.com/index.htm'))
        )
        self.assertTrue(
            HTMLReader.is_url(URLInfo.parse('example.com/index.html'))
        )
        self.assertTrue(
            HTMLReader.is_url(URLInfo.parse('example.com/index.dhtm'))
        )
        self.assertTrue(
            HTMLReader.is_url(URLInfo.parse('example.com/index.xhtml'))
        )
        self.assertTrue(
            HTMLReader.is_url(URLInfo.parse('example.com/index.xht'))
        )
        self.assertFalse(
            HTMLReader.is_url(URLInfo.parse('example.com/image.jpg'))
        )
        self.assertTrue(
            HTMLReader.is_request(Request('example.com/index.html'))
        )
        self.assertFalse(
            HTMLReader.is_request(Request('example.com/image.jpg'))
        )

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'text/html'
        self.assertTrue(HTMLReader.is_response(response))

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'image/png'
        self.assertFalse(HTMLReader.is_response(response))

    def test_html_parse_doctype(self):
        html_parser = self.get_html_parser()

        self.assertIn(
            'html',
            html_parser.parse_doctype(
                io.BytesIO(b'<!DOCTYPE HTML><html></html>')
            )
        )
        self.assertIn(
            'XHTML',
            html_parser.parse_doctype(
                io.BytesIO(b'''
                <!DOCTYPE html PUBLIC
                "-//W3C//DTD XHTML 1.0 Transitional//EN"
                "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
                <html></html>
                ''')
            )
        )
        self.assertFalse(html_parser.parse_doctype(io.BytesIO(b'hello world!')))
        self.assertFalse(html_parser.parse_doctype(io.BytesIO(b'')))
        self.assertFalse(html_parser.parse_doctype(io.BytesIO(b'\x00')))
        self.assertFalse(html_parser.parse_doctype(io.BytesIO(b'A\xfe')))

    def test_html_encoding(self):
        reader = HTMLReader(self.get_html_parser())

        for name in CODEC_NAMES:
            data = io.BytesIO('<img>'.encode(name))
            elements = tuple(reader.iter_elements(data, encoding=name))
            html_element = elements[0]
            self.assertEqual('html', html_element.tag)

    def test_html_layout(self):
        reader = HTMLReader(self.get_html_parser())

        elements = tuple(
            reader.iter_elements(io.BytesIO(b'''
            <html>
                <head>
                    <title>hi</title>
                </head>
                <body>
                    <img>
                </body>
            </html>'''), encoding='ascii')
        )

        print(elements)

        self.assertEqual('html', elements[0].tag)
        self.assertEqual('head', elements[1].tag)
        self.assertEqual('title', elements[2].tag)
        self.assertEqual('title', elements[3].tag)
        self.assertEqual('head', elements[4].tag)
        self.assertEqual('body', elements[5].tag)
        self.assertEqual('img', elements[6].tag)
        self.assertEqual('img', elements[7].tag)
        self.assertEqual('body', elements[8].tag)
        self.assertEqual('html', elements[9].tag)

    def test_html_early_html(self):
        reader = HTMLReader(self.get_html_parser())

        for test_string in [
            b'''<!DOCTYPE HTML><html></html><img>''',
            b'''<html></html><img>''',
            b'''<!DOCTYPE HTML><img><html></html>''',
            b'''<img><html></html>''',
            b'''<!DOCTYPE HTML>
                <html><body></body></html><p><img>''',
            b'''
                <html><body></body></html><p><img>''',
            b'''
                <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
                "http://www.w3.org/TR/html4/loose.dtd">
                <html>
                <head>
                <title>Download</title>
                </head>
                <body>
                <br />
                </body>
                </html>
                <pre><img></pre>
            ''',
            b'''
                <html>
                <head>
                <title>Download</title>
                </head>
                <body>
                <br />
                </body>
                </html>
                <pre><img></pre>
            ''',
            b'''
                <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"
                "http://www.w3.org/TR/html4/loose.dtd">
                <html>
                <body>
                <br />
                </body>
                <head>
                <title>Download</title>
                </head>
                </html>
                <pre><img></pre>
            ''',
            b'''
                <html>
                <body>
                <br />
                </body>
                <head>
                <title>Download</title>
                </head>
                </html>
                <pre><img></pre>
            ''',
        ]:
            elements = tuple(
                reader.iter_elements(io.BytesIO(test_string), encoding='ascii')
            )
            print(elements)
            element_tags = tuple(element.tag for element in elements)
            self.assertIn('img', element_tags)


class TestLxmlHTML(Mixin, unittest.TestCase):
    def get_html_parser(self):
        return LxmlHTMLParser()
