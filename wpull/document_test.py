# encoding=utf-8
import io

from wpull.backport.testing import unittest
from wpull.document import HTMLReader, SitemapReader, CSSReader


CODEC_NAMES = (
    'ascii',
    'big5',
    'big5hkscs',
    'cp037',
    'cp424',
    'cp437',
    'cp500',
    # 'cp720',  # not in py 2.6
    'cp737',
    'cp775',
    'cp850',
    'cp852',
    'cp855',
    'cp856',
    'cp857',
    # 'cp858',  # not in py 2.6
    'cp860',
    'cp861',
    'cp862',
    'cp863',
    'cp864',
    'cp865',
    'cp866',
    'cp869',
    'cp874',
    'cp875',
    'cp932',
    'cp949',
    'cp950',
    'cp1006',
    'cp1026',
    'cp1140',
    'cp1250',
    'cp1251',
    'cp1252',
    'cp1253',
    'cp1254',
    'cp1255',
    'cp1256',
    'cp1257',
    'cp1258',
    # 'cp65001',  # windows only
    'euc_jp',
    'euc_jis_2004',
    'euc_jisx0213',
    'euc_kr',
    'gb2312',
    'gbk',
    'gb18030',
    'hz',
    'iso2022_jp',
    'iso2022_jp_1',
    'iso2022_jp_2',
    'iso2022_jp_2004',
    'iso2022_jp_3',
    'iso2022_jp_ext',
    'iso2022_kr',
    'latin_1',
    'iso8859_2',
    'iso8859_3',
    'iso8859_4',
    'iso8859_5',
    'iso8859_6',
    'iso8859_7',
    'iso8859_8',
    'iso8859_9',
    'iso8859_10',
    'iso8859_13',
    'iso8859_14',
    'iso8859_15',
    'iso8859_16',
    'johab',
    'koi8_r',
    'koi8_u',
    'mac_cyrillic',
    'mac_greek',
    'mac_iceland',
    'mac_latin2',
    'mac_roman',
    'mac_turkish',
    'ptcp154',
    'shift_jis',
    'shift_jis_2004',
    'shift_jisx0213',
    'utf_32',
    'utf_32_be',
    'utf_32_le',
    'utf_16',
    'utf_16_be',
    'utf_16_le',
    'utf_7',
    'utf_8',
    'utf_8_sig',
)
EBCDIC = (
    'cp037',
    'cp424',
    'cp500',
    'cp875',
    'cp1026',
    'cp1140',
)


class TestDocument(unittest.TestCase):
    def test_html_encoding(self):
        reader = HTMLReader()

        for name in CODEC_NAMES:
            data = io.BytesIO('<img>'.encode(name))
            elements = tuple(reader.read_links(data, encoding=name))
            html_element = elements[0]
            self.assertEqual('html', html_element.tag)

    def test_sitemap_encoding(self):
        reader = SitemapReader()

        for name in CODEC_NAMES:
            if name in EBCDIC or name == 'utf_8_sig':
                # FIXME: we're assuming that all codecs are ASCII backward
                # compatable
                continue

            data = io.BytesIO(
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<urlset><url><loc>blah</loc></url></urlset>'.encode(name)
            )
            print('->', name)
            links = tuple(reader.read_links(data, encoding=name))
            link = links[0]
            self.assertEqual('blah', link)

    def test_html_layout(self):
        reader = HTMLReader()

        elements = tuple(
            reader.read_tree(io.BytesIO(b'''
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
        reader = HTMLReader()

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
                reader.read_links(io.BytesIO(test_string), encoding='ascii')
            )
            self.assertEqual('img', elements[-1].tag)
            elements = tuple(
                reader.read_tree(io.BytesIO(test_string), encoding='ascii')
            )
            self.assertEqual('img', elements[-4].tag)

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

        for link in \
        reader.read_links(io.BytesIO(css_data), encoding='ascii'):
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

        for link in \
        reader.read_links(io.BytesIO(css_data), encoding='ascii'):
            links.add(link)

        self.assertEqual(len(links), 200000)
