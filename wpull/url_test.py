# encoding=utf-8
from wpull.backport.testing import unittest
from wpull.url import (URLInfo, BackwardDomainFilter, TriesFilter, LevelFilter,
    ParentFilter, RecursiveFilter, SpanHostsFilter, RegexFilter, HTTPFilter,
    HostnameFilter, schemes_similar, is_subdir, DirectoryFilter)


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
        self.assertEqual(
            'http://example.com/asdf/ghjk/',
            URLInfo.parse(
                'HTTP://username:password@example.com/asdf/ghjk/').url
        )
        self.assertEqual(
            'http://example.com/ð',
            URLInfo.parse('http://example.com/ð').url
        )
        self.assertEqual(
            'http://example.com/ð',
            URLInfo.parse('http://example.com/ð').url
        )
        self.assertEqual(
            'mailto:user@example.com',
            URLInfo.parse('mailto:user@example.com').url
        )
        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('http://example.com:80').url
        )

    def test_url_info_to_dict(self):
        url_info = URLInfo.parse('https://example.com/file.jpg')
        url_info_dict = url_info.to_dict()
        self.assertEqual('/file.jpg', url_info_dict['path'])
        self.assertEqual('example.com', url_info_dict['hostname'])
        self.assertEqual('https', url_info_dict['scheme'])
        self.assertEqual(443, url_info_dict['port'])

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
