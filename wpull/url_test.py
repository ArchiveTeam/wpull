# encoding=utf-8

from wpull.backport.testing import unittest
from wpull.url import (URLInfo, BackwardDomainFilter, TriesFilter, LevelFilter,
    ParentFilter, RecursiveFilter, SpanHostsFilter, RegexFilter, HTTPFilter,
    HostnameFilter, schemes_similar, is_subdir, DirectoryFilter, unquote,
    unquote_plus, quote, quote_plus, split_query, uppercase_percent_encoding,
    urljoin)


class MockURLTableRecord(object):
    def __init__(self):
        self.url = None
        self.try_count = None
        self.level = None
        self.referrer = None
        self.inline = None
        self.top_url = None


class TestURL(unittest.TestCase):
    def test_url_info(self):
        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('example.com').url
        )
        self.assertEqual(
            80,
            URLInfo.parse('http://example.com').port
        )
        self.assertEqual(
            443,
            URLInfo.parse('https://example.com').port
        )
        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('example.com/').url
        )
        self.assertEqual(
            'https://example.com/',
            URLInfo.parse('https://example.com').url
        )
        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('//example.com').url
        )
        self.assertEqual(
            'http://example.com:8080/',
            URLInfo.parse('example.com:8080').url
        )
        self.assertEqual(
            8080,
            URLInfo.parse('example.com:8080').port
        )
        self.assertEqual(
            'http://example.com/asdf',
            URLInfo.parse('example.com/asdf#blah').url
        )
        self.assertEqual(
            'http://example.com/asdf/ghjk',
            URLInfo.parse('example.com/asdf/ghjk#blah').url
        )

        url_info = URLInfo.parse(
            'HTTP://username:password@example.com/asdf/ghjk/')
        self.assertEqual(
            'http://example.com/asdf/ghjk/',
            url_info.url
        )
        self.assertEqual(
            'http',
            url_info.scheme
        )
        self.assertEqual(
            'username',
            url_info.username
        )
        self.assertEqual(
            'password',
            url_info.password
        )
        self.assertEqual(
            'utf-8',
            url_info.encoding
        )

        self.assertEqual(
            'http://example.com/%C3%B0',
            URLInfo.parse('http://example.com/ð').url
        )

        url_info = URLInfo.parse('mailto:user@example.com')
        self.assertEqual(
            'mailto:user@example.com',
            url_info.url
        )
        self.assertEqual(
            'mailto',
            url_info.scheme
        )

        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('http://example.com:80').url
        )
        self.assertRaises(ValueError, URLInfo.parse, '')
        self.assertRaises(ValueError, URLInfo.parse, '#')
        self.assertRaises(ValueError, URLInfo.parse, 'http://')

        self.assertEqual(
            'http://example.com/blah',
            URLInfo.parse('//example.com/blah').url
        )
        self.assertEqual(
            'http://example.com/blah%20blah/',
            URLInfo.parse('example.com/blah blah/').url
        )
        self.assertEqual(
            'http://example.com/blah%20blah/',
            URLInfo.parse('example.com/blah%20blah/').url
        )
        self.assertEqual(
            'http://www.xn--hda.com/asdf',
            URLInfo.parse('www.ð.com/asdf').url
        )
        self.assertEqual(
            'www.xn--hda.com',
            URLInfo.parse('www.ð.com/asdf').hostname
        )
        self.assertEqual(
            'http://example.com/?blah=%C3%B0',
            URLInfo.parse('example.com?blah=ð').url
        )
        self.assertEqual(
            'http://example.com/?blah=%C3%B0',
            URLInfo.parse('example.com?blah=%c3%b0').url
        )

        url_info = URLInfo.parse('example.com/文字化け/?blah=文字化け',
            encoding='shift_jis')
        self.assertEqual(
            'http://example.com/%95%B6%8E%9A%89%BB%82%AF/'
                '?blah=%95%B6%8E%9A%89%BB%82%AF',
            url_info.url
        )
        self.assertEqual(
            '/%95%B6%8E%9A%89%BB%82%AF/',
            url_info.path
        )
        self.assertEqual(
            'blah=%95%B6%8E%9A%89%BB%82%AF',
            url_info.query
        )
        self.assertEqual(
            'shift_jis',
            url_info.encoding
        )

        self.assertEqual(
            'http://example.com/%95%B6%8E%9A%89%BB%82%AF/'
                '?blah=%95%B6%8E%9A%89%BB%82%AF',
            URLInfo.parse('example.com/%95%B6%8E%9A%89%BB%82%AF/'
                '?blah=%95%B6%8E%9A%89%BB%82%AF', encoding='shift_jis').url
        )
        self.assertEqual(
            'http://example.com/%95%B6%8E%9A%89%BB%82%AF/'
                '?blah=%95%B6%8E%9A%89%BB%82%AF',
            URLInfo.parse('example.com/%95%B6%8E%9A%89%BB%82%AF/'
                '?blah=%95%B6%8E%9A%89%BB%82%AF').url
        )

        self.assertEqual(
            'http://example.com/'
                '?blah=http%3A%2F%2Fexample.com%2F%3Ffail%3Dtrue',
            URLInfo.parse(
                'http://example.com/'
                    '?blah=http%3A%2F%2Fexample.com%2F%3Ffail%3Dtrue').url
        )
        self.assertEqual(
            'http://example.com/'
                '?blah=http%3A%2F%2Fexample.com%2F%3Ffail%3Dtrue',
            URLInfo.parse(
                'http://example.com/'
                    '?blah=http://example.com/?fail%3Dtrue').url
        )

    def test_url_info_to_dict(self):
        url_info = URLInfo.parse('https://example.com/file.jpg')
        url_info_dict = url_info.to_dict()
        self.assertEqual('/file.jpg', url_info_dict['path'])
        self.assertEqual('example.com', url_info_dict['hostname'])
        self.assertEqual('https', url_info_dict['scheme'])
        self.assertEqual(443, url_info_dict['port'])
        self.assertEqual('utf-8', url_info_dict['encoding'])

    def test_http_filter(self):
        mock_record = MockURLTableRecord()

        url_filter = HTTPFilter()
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('mailto:user@example.com'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse("javascript:alert('hello!')"),
            mock_record
        ))

    def test_wget_domain_filter(self):
        url_filter = BackwardDomainFilter(
            accepted=['g.example.com', 'cdn.example.com', 'cdn.test'])

        self.assertTrue(
            url_filter.test(URLInfo.parse('g.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('blog.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('cdn.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('server1.cdn.test'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse("javascript:alert('hello!')"), None))

        url_filter = BackwardDomainFilter(
            accepted=['g.example.com', 'cdn.example.com', 'cdn.test'],
            rejected=['blog.example.com']
        )

        self.assertTrue(
            url_filter.test(URLInfo.parse('g.example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('blog.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('cdn.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('server1.cdn.test'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('example.com'), None))

    def test_hostname_filter(self):
        url_filter = HostnameFilter(
            accepted=['g.example.com', 'cdn.example.com', 'cdn.test'])

        self.assertTrue(
            url_filter.test(URLInfo.parse('g.example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('blog.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('cdn.example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('server1.cdn.test'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse("javascript:alert('hello!')"), None))

        url_filter = HostnameFilter(
            accepted=['g.example.com', 'cdn.example.com', 'cdn.test'],
            rejected=['blog.example.com']
        )

        self.assertTrue(
            url_filter.test(URLInfo.parse('g.example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('blog.example.com'), None))
        self.assertTrue(
            url_filter.test(URLInfo.parse('cdn.example.com'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('server1.cdn.test'), None))
        self.assertFalse(
            url_filter.test(URLInfo.parse('example.com'), None))

    def test_recursive_filter_off(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 0
        url_filter = RecursiveFilter(False, False)

        self.assertTrue(url_filter.test(None, mock_record))

        mock_record.level = 1
        self.assertFalse(url_filter.test(None, mock_record))

    def test_recursive_filter_on(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 0
        url_filter = RecursiveFilter(True, False)

        self.assertTrue(url_filter.test(None, mock_record))

        mock_record.level = 1
        self.assertTrue(url_filter.test(None, mock_record))

    def test_recursive_filter_requisites(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 0
        mock_record.inline = True
        url_filter = RecursiveFilter(False, True)

        self.assertTrue(url_filter.test(None, mock_record))

    def test_level_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 4
        url_filter = LevelFilter(0)
        self.assertTrue(url_filter.test(None, mock_record))

        url_filter = LevelFilter(5)
        mock_record.level = 5
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.level = 6
        self.assertFalse(url_filter.test(None, mock_record))

    def test_tries_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.try_count = 4
        url_filter = TriesFilter(0)
        self.assertTrue(url_filter.test(None, mock_record))

        url_filter = TriesFilter(5)
        mock_record.try_count = 4
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.try_count = 5
        self.assertFalse(url_filter.test(None, mock_record))

    def test_parent_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.inline = False
        url_filter = ParentFilter()

        mock_record.top_url = 'http://example.com/blog/topic2/'
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic2/'),
            mock_record
        ))
        mock_record.top_url = 'http://example.com/blog/topic1/'
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            mock_record
        ))

        mock_record.inline = True
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/styles.css'),
            mock_record
        ))

    def test_span_hosts_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.url = 'http://example.com'

        url_filter = SpanHostsFilter([
                URLInfo.parse('http://example.com/blog/'),
            ],
            enabled=False
        )

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://hotdog.example/blog/topic1/blah.html'),
            mock_record
        ))

        url_filter = SpanHostsFilter([
                URLInfo.parse('http://example.com/blog/'),
            ],
            enabled=True
        )
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://hotdog.example/blog/topic1/blah.html'),
            mock_record
        ))

    def test_regex_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.url = 'http://example.com/blog/'

        url_filter = RegexFilter()
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net'),
            mock_record
        ))

        url_filter = RegexFilter(accepted=r'blo[a-z]/$')
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net/blob/'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net/blob/123'),
            mock_record
        ))

        url_filter = RegexFilter(rejected=r'\.gif$')
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net/blob/'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net/blob/123.gif'),
            mock_record
        ))

    def test_directory_filter(self):
        mock_record = MockURLTableRecord()
        mock_record.url = 'http://example.com/blog/'

        url_filter = DirectoryFilter()

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com'),
            mock_record
        ))

        url_filter = DirectoryFilter(accepted=['/blog'])

        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com'),
            mock_record
        ))

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            mock_record
        ))

        url_filter = DirectoryFilter(rejected=['/cgi-bin/'])

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com/cgi-bin'),
            mock_record
        ))

    def test_schemes_simialar(self):
        self.assertTrue(schemes_similar('http', 'http'))
        self.assertTrue(schemes_similar('https', 'http'))
        self.assertTrue(schemes_similar('http', 'https'))
        self.assertTrue(schemes_similar('https', 'https'))
        self.assertFalse(schemes_similar('ftp', 'http'))
        self.assertTrue(schemes_similar('email', 'email'))

    def test_is_subdir(self):
        self.assertTrue(is_subdir('/profile/blog', '/profile/blog/123'))
        self.assertTrue(is_subdir('/profile/blog/', '/profile/blog/123'))
        self.assertFalse(is_subdir('/profile/blog', '/profile/photo'))

        self.assertTrue(is_subdir('/profile/blog', '/profile/blog/123',
            trailing_slash=True))
        self.assertTrue(is_subdir('/profile/blog/', '/profile/blog/123',
            trailing_slash=True))
        self.assertFalse(is_subdir('/profile/blog/', '/profile/photo',
            trailing_slash=True))
        self.assertTrue(is_subdir('/profile/blog', '/profile/photo',
            trailing_slash=True))

        self.assertTrue(is_subdir('/profile/blog-*-', '/profile/blog-1-/',
            wildcards=True))
        self.assertFalse(is_subdir('/profile/blog-*-', '/profile/blog/',
            wildcards=True))
        self.assertFalse(is_subdir('/profile/blog-*-', '/profile/',
            wildcards=True))

    def test_split_query(self):
        self.assertEqual([],
            split_query('&'))
        self.assertEqual([('a', 'ð')],
            split_query('a=ð'))
        self.assertEqual([('a', 'ð')],
            split_query('a=ð&b'))
        self.assertEqual([('a', 'ð')],
            split_query('a=ð&b='))
        self.assertEqual([('a', 'ð'), ('b', '')],
            split_query('a=ð&b=', keep_blank_values=True))
        self.assertEqual([('a', 'ð'), ('b', '%2F')],
            split_query('a=ð&b=%2F'))

    def test_url_quote(self):
        self.assertEqual('a ', unquote('a%20'))
        self.assertEqual('að', unquote('a%C3%B0'))
        self.assertEqual('a ', unquote_plus('a+'))
        self.assertEqual('að', unquote_plus('a%C3%B0'))
        self.assertEqual('a%20', quote('a '))
        self.assertEqual('a%C3%B0', quote('að'))
        self.assertEqual('a+', quote_plus('a '))
        self.assertEqual('a%C3%B0', quote_plus('að'))

    def test_uppercase_percent_encoding(self):
        self.assertEqual(
            'ð',
            uppercase_percent_encoding('ð')
        )
        self.assertEqual(
            'qwerty%%asdf',
            uppercase_percent_encoding('qwerty%%asdf')
        )
        self.assertEqual(
            'cAt%2F%EE%AB',
            uppercase_percent_encoding('cAt%2f%ee%ab')
        )

    def test_url_join(self):
        self.assertEqual(
            'http://example.net',
            urljoin('http://example.com', '//example.net')
        )
        self.assertEqual(
            'https://example.net',
            urljoin('https://example.com', '//example.net')
        )
        self.assertEqual(
            'https://example.com/asdf',
            urljoin('https://example.com/cookies', '/asdf')
        )
        self.assertEqual(
            'http://example.com/asdf',
            urljoin('http://example.com/cookies', 'asdf')
        )
        self.assertEqual(
            'http://example.com/cookies/asdf',
            urljoin('http://example.com/cookies/', 'asdf')
        )
        self.assertEqual(
            'https://example.net/asdf',
            urljoin('https://example.net/', '/asdf')
        )
        self.assertEqual(
            'http://example.net/asdf',
            urljoin('https://example.com', 'http://example.net/asdf')
        )
        self.assertEqual(
            'http://example.com/',
            urljoin('http://example.com', '//example.com/')
        )
