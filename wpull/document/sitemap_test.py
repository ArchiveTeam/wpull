import gzip
import io
import unittest

from wpull.document.base_test import CODEC_NAMES, EBCDIC
from wpull.document.htmlparse.html5lib_ import HTMLParser as HTML5LibHTMLParser
from wpull.document.sitemap import SitemapReader
from wpull.http.request import Request
from wpull.url import URLInfo
from wpull.util import IS_PYPY


if not IS_PYPY:
    from wpull.document.htmlparse.lxml_ import HTMLParser as LxmlHTMLParser
else:
    LxmlHTMLParser = type(NotImplemented)


class Mixin(object):
    def get_html_parser(self):
        raise NotImplementedError()

    def test_sitemap_encoding(self):
        reader = SitemapReader(self.get_html_parser())

        for name in CODEC_NAMES:
            if name in EBCDIC or name == 'utf_8_sig':
                # XXX: we're assuming that all codecs are ASCII backward
                # compatable
                continue

            if name.endswith('_le') or name.endswith('_be'):
                # XXX: Assume BOM is always included
                continue

            data = io.BytesIO(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset><url><loc>blah</loc></url></urlset>'.encode(name)
            )
            print('->', name)
            links = tuple(reader.iter_links(data, encoding=name))
            link = links[0]
            self.assertEqual('blah', link)

    def test_sitemap_detect(self):
        # It should detect without BOM
        self.assertTrue(SitemapReader.is_file(
            io.BytesIO('<?xml > <urlset >'.encode('utf-16le'))
        ))
        self.assertFalse(SitemapReader.is_file(
            io.BytesIO('<!DOCTYPE html><html><body>'.encode('utf-16le'))
        ))
        self.assertFalse(SitemapReader.is_file(
            io.BytesIO(b'<html><body>hello<urlset>')
        ))
        self.assertTrue(SitemapReader.is_file(
            io.BytesIO(b'<?xml version> <urlset>')
        ))

        data_file = io.BytesIO()
        g_file = gzip.GzipFile(fileobj=data_file, mode='wb')
        g_file.write('<?xml version> <urlset>'.encode('utf-16le'))
        g_file.close()
        data_file.seek(0)
        self.assertTrue(SitemapReader.is_file(
            data_file
        ))

        self.assertTrue(
            SitemapReader.is_url(URLInfo.parse('example.com/sitemaps1.xml'))
        )
        self.assertTrue(
            SitemapReader.is_url(URLInfo.parse('example.com/robots.txt'))
        )
        self.assertFalse(
            SitemapReader.is_url(URLInfo.parse('example.com/image.jpg'))
        )
        self.assertTrue(
            SitemapReader.is_request(Request('example.com/sitemaps34.xml'))
        )
        self.assertFalse(
            SitemapReader.is_request(Request('example.com/image.jpg'))
        )


@unittest.skipIf(IS_PYPY, 'Not supported under PyPy')
class TestLxmlSitemap(Mixin, unittest.TestCase):
    def get_html_parser(self):
        return LxmlHTMLParser()


class TestHTML5LibSitemap(Mixin, unittest.TestCase):
    def get_html_parser(self):
        return HTML5LibHTMLParser()
