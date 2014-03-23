# encoding=utf-8
import io

from wpull.backport.testing import unittest
from wpull.document import HTMLReader, SitemapReader


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
            tree = reader.parse(data, encoding=name)
            html_element = tree.getroot()
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
                '<urlset><url>blah</url></urlset>'.encode(name)
            )
            print('->', name)
            tree = reader.parse(data, encoding=name)
            urlset_element = tree.getroot()
            self.assertEqual('urlset', urlset_element.tag)
