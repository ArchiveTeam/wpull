# encoding=utf-8

import unittest

from wpull.url import URLInfo
from wpull.urlfilter import (SchemeFilter, HTTPSOnlyFilter, BackwardDomainFilter,
                             HostnameFilter, RecursiveFilter, LevelFilter,
                             TriesFilter, ParentFilter, SpanHostsFilter,
                             RegexFilter, DirectoryFilter,
                             BackwardFilenameFilter, FollowFTPFilter)


class MockURLTableRecord(object):
    def __init__(self):
        self.url = None
        self.try_count = None
        self.level = None
        self.referrer = None
        self.inline = None
        self.top_url = None

    @property
    def referrer_info(self):
        return URLInfo.parse(self.referrer)


class TestURLFilter(unittest.TestCase):
    def test_scheme_filter(self):
        mock_record = MockURLTableRecord()

        url_filter = SchemeFilter()
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.net'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://example.net'),
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

    def test_https_filter(self):
        mock_record = MockURLTableRecord()

        url_filter = HTTPSOnlyFilter()
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.net'),
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

    def test_follow_ftp_filter(self):
        mock_record = MockURLTableRecord()
        url_filter = FollowFTPFilter()

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            mock_record
        ))

        mock_record.referrer = 'http://wolf.farts'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            mock_record
        ))

        url_filter = FollowFTPFilter(follow=True)

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            mock_record
        ))

        mock_record.referrer = 'ftp://wolf.farts'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            mock_record
        ))

        url_filter = FollowFTPFilter(follow=True)

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
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
        url_filter = RecursiveFilter()

        self.assertTrue(url_filter.test(None, mock_record))

        mock_record.level = 1
        self.assertFalse(url_filter.test(None, mock_record))

    def test_recursive_filter_on(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 0
        url_filter = RecursiveFilter(enabled=True)

        self.assertTrue(url_filter.test(None, mock_record))

        mock_record.level = 1
        self.assertTrue(url_filter.test(None, mock_record))

    def test_recursive_filter_requisites(self):
        mock_record = MockURLTableRecord()
        mock_record.level = 0
        mock_record.inline = 1
        url_filter = RecursiveFilter(page_requisites=True)

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

        url_filter = LevelFilter(5)
        mock_record.inline = 1
        mock_record.level = 5
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.level = 6
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.level = 7
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.level = 8
        self.assertFalse(url_filter.test(None, mock_record))

        url_filter = LevelFilter(0)
        mock_record.inline = 1
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 2
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 3
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 4
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 5
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 6
        self.assertFalse(url_filter.test(None, mock_record))

        mock_record.level = 1

        url_filter = LevelFilter(0, inline_max_depth=0)
        mock_record.inline = 1000
        self.assertTrue(url_filter.test(None, mock_record))

        url_filter = LevelFilter(5, inline_max_depth=1)
        mock_record.inline = 1
        self.assertTrue(url_filter.test(None, mock_record))
        mock_record.inline = 2
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
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.com/blog/topic1/blah2.html'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('https://example.com/blog/'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://somewhere.com/'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://somewhere.com/'),
            mock_record
        ))

        mock_record.inline = 1
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

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/'),
        ],
            page_requisites=True
        )
        mock_record = MockURLTableRecord()
        mock_record.url = 'http://1.example.com/'
        mock_record.inline = 1

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://1.example.com/'),
            mock_record
        ))

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/'),
        ],
            linked_pages=True,
        )
        mock_record = MockURLTableRecord()
        mock_record.url = 'http://1.example.com/'
        mock_record.referrer = 'http://example.com/blog/'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://1.example.com/'),
            mock_record
        ))

        mock_record = MockURLTableRecord()
        mock_record.url = 'http://1.example.com/blah.html'
        mock_record.referrer = 'http://1.example.com/'

        self.assertFalse(url_filter.test(
            URLInfo.parse('http://1.example.com/blah.html'),
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

    def test_backward_filename_filter(self):
        url_filter = BackwardFilenameFilter(
            accepted=['html', 'image.*.png'],
            rejected=['bmp', 'jp[eg]', 'image.123.png']
        )

        mock_record = MockURLTableRecord()
        mock_record.url = 'http://example.com/'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example/index.html'),
            mock_record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example/myimage.1003.png'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/myimage.123.png'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/blah.png'),
            mock_record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/image.1003.png.bmp'),
            mock_record
        ))
