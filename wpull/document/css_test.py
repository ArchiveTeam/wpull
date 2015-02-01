import io
import unittest

from wpull.document.css import CSSReader
from wpull.http.request import Request, Response
from wpull.url import URLInfo


class TestCSS(unittest.TestCase):
    def test_css_detect(self):
        self.assertTrue(CSSReader.is_file(
            io.BytesIO('body { color: white }'.encode('utf-16le'))
        ))
        self.assertFalse(CSSReader.is_file(
            io.BytesIO('hello world!'.encode('utf-16le'))
        ))
        self.assertFalse(CSSReader.is_file(
            io.BytesIO(b'<html><body>hello')
        ))
        self.assertTrue(CSSReader.is_file(
            io.BytesIO(b'h1 { background-color: red }')
        ))
        self.assertTrue(CSSReader.is_file(
            io.BytesIO(b'@import url.css;')
        ))
        self.assertTrue(
            CSSReader.is_url(URLInfo.parse('example.com/index.css'))
        )
        self.assertFalse(
            CSSReader.is_url(URLInfo.parse('example.com/image.jpg'))
        )
        self.assertTrue(
            CSSReader.is_request(Request('example.com/index.css'))
        )
        self.assertFalse(
            CSSReader.is_request(Request('example.com/image.jpg'))
        )

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'text/css'
        self.assertTrue(CSSReader.is_response(response))

        response = Response(200, 'OK')
        response.fields['Content-Type'] = 'image/png'
        self.assertFalse(CSSReader.is_response(response))

    def test_css_links_simple(self):
        css_data = b'''@import url('wow.css');
            body { background: url('cool.png') }
        '''
        reader = CSSReader()
        links = set()

        for link in reader.iter_links(
                io.BytesIO(css_data), encoding='ascii', context=True):
            links.add(link)

        self.assertEqual(
            {
                ('wow.css', 'import'),
                ('cool.png', 'url')
            },
            links
        )

    def test_css_read_links_big(self):
        css_data = b'\n'.join(
            [
                'url(blah{0});'.format(num).encode('ascii')
                for num in range(100000)
            ]
        )
        reader = CSSReader()

        self.assertGreater(len(css_data), reader.BUFFER_SIZE)

        links = set()

        for link in reader.iter_links(
                io.BytesIO(css_data), encoding='ascii'):
            links.add(link)

        self.assertEqual(len(links), 100000)

    def test_css_read_links_huge(self):
        css_data = b'\n'.join(
            [
                'url(blah{0});'.format(num).encode('ascii')
                for num in range(200000)
            ]
        )
        reader = CSSReader()

        self.assertGreater(len(css_data), reader.BUFFER_SIZE)

        links = set()

        for link in reader.iter_links(
                io.BytesIO(css_data), encoding='ascii'):
            links.add(link)

        self.assertEqual(len(links), 200000)
