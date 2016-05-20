# encoding=utf-8

import unittest

from wpull.pipeline.item import URLRecord
from wpull.url import URLInfo
from wpull.urlfilter import (SchemeFilter, HTTPSOnlyFilter, BackwardDomainFilter,
                             HostnameFilter, RecursiveFilter, LevelFilter,
                             TriesFilter, ParentFilter, SpanHostsFilter,
                             RegexFilter, DirectoryFilter,
                             BackwardFilenameFilter, FollowFTPFilter)


class TestURLFilter(unittest.TestCase):
    def test_scheme_filter(self):
        record = URLRecord()

        url_filter = SchemeFilter()
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.net'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://example.net'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('mailto:user@example.com'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse("javascript:alert('hello!')"),
            record
        ))

    def test_https_filter(self):
        record= URLRecord()

        url_filter = HTTPSOnlyFilter()
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.net'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('mailto:user@example.com'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse("javascript:alert('hello!')"),
            record
        ))

    def test_follow_ftp_filter(self):
        record = URLRecord()
        url_filter = FollowFTPFilter()

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            record
        ))

        record.parent_url = 'http://wolf.farts'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            record
        ))

        url_filter = FollowFTPFilter(follow=True)

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            record
        ))

        record.parent_url = 'ftp://wolf.farts'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            record
        ))

        url_filter = FollowFTPFilter(follow=True)

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://wolf.farts/1'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('mailto:wolf@wolf.farts'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('ftp://wolf.farts/'),
            record
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
        record = URLRecord()
        record.level = 0
        url_filter = RecursiveFilter()

        self.assertTrue(url_filter.test(None, record))

        record.level = 1
        self.assertFalse(url_filter.test(None, record))

    def test_recursive_filter_on(self):
        record = URLRecord()
        record.level = 0
        url_filter = RecursiveFilter(enabled=True)

        self.assertTrue(url_filter.test(None, record))

        record.level = 1
        self.assertTrue(url_filter.test(None, record))

    def test_recursive_filter_requisites(self):
        record = URLRecord()
        record.level = 0
        record.inline_level = 1
        url_filter = RecursiveFilter(page_requisites=True)

        self.assertTrue(url_filter.test(None, record))

    def test_level_filter(self):
        record = URLRecord()
        record.level = 4
        url_filter = LevelFilter(0)
        self.assertTrue(url_filter.test(None, record))

        url_filter = LevelFilter(5)
        record.level = 5
        self.assertTrue(url_filter.test(None, record))
        record.level = 6
        self.assertFalse(url_filter.test(None, record))

        url_filter = LevelFilter(5)
        record.inline_level = 1
        record.level = 5
        self.assertTrue(url_filter.test(None, record))
        record.level = 6
        self.assertTrue(url_filter.test(None, record))
        record.level = 7
        self.assertTrue(url_filter.test(None, record))
        record.level = 8
        self.assertFalse(url_filter.test(None, record))

        url_filter = LevelFilter(0)
        record.inline_level = 1
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 2
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 3
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 4
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 5
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 6
        self.assertFalse(url_filter.test(None, record))

        record.level = 1

        url_filter = LevelFilter(0, inline_max_depth=0)
        record.inline_level = 1000
        self.assertTrue(url_filter.test(None, record))

        url_filter = LevelFilter(5, inline_max_depth=1)
        record.inline_level = 1
        self.assertTrue(url_filter.test(None, record))
        record.inline_level = 2
        self.assertFalse(url_filter.test(None, record))

    def test_tries_filter(self):
        record = URLRecord()
        record.try_count = 4
        url_filter = TriesFilter(0)
        self.assertTrue(url_filter.test(None, record))

        url_filter = TriesFilter(5)
        record.try_count = 4
        self.assertTrue(url_filter.test(None, record))
        record.try_count = 5
        self.assertFalse(url_filter.test(None, record))

    def test_parent_filter(self):
        record = URLRecord()
        url_filter = ParentFilter()

        record.root_url = 'http://example.com/blog/topic2/'
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic2/'),
            record
        ))
        record.root_url = 'http://example.com/blog/topic1/'
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://example.com/blog/topic1/blah2.html'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('https://example.com/blog/'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://somewhere.com/'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('https://somewhere.com/'),
            record
        ))

        record.inline_level = 1
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/styles.css'),
            record
        ))

    def test_span_hosts_filter(self):
        record = URLRecord()
        record.url = 'http://example.com'

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/').hostname,
        ],
            enabled=False
        )

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://hotdog.example/blog/topic1/blah.html'),
            record
        ))

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/').hostname,
        ],
            enabled=True
        )
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/topic1/blah.html'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://hotdog.example/blog/topic1/blah.html'),
            record
        ))

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/').hostname,
        ],
            page_requisites=True
        )
        record = URLRecord()
        record.url = 'http://1.example.com/'
        record.inline_level = 1

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://1.example.com/'),
            record
        ))

        url_filter = SpanHostsFilter([
            URLInfo.parse('http://example.com/blog/').hostname,
        ],
            linked_pages=True,
        )
        record = URLRecord()
        record.url = 'http://1.example.com/'
        record.parent_url = 'http://example.com/blog/'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://1.example.com/'),
            record
        ))

        record = URLRecord()
        record.url = 'http://1.example.com/blah.html'
        record.parent_url = 'http://1.example.com/'

        self.assertFalse(url_filter.test(
            URLInfo.parse('http://1.example.com/blah.html'),
            record
        ))

    def test_regex_filter(self):
        record = URLRecord()
        record.url = 'http://example.com/blog/'

        url_filter = RegexFilter()
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net'),
            record
        ))

        url_filter = RegexFilter(accepted=r'blo[a-z]/$')
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net/blob/'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net/blob/123'),
            record
        ))

        url_filter = RegexFilter(rejected=r'\.gif$')
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.net/blob/'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.net/blob/123.gif'),
            record
        ))

    def test_directory_filter(self):
        record = URLRecord()
        record.url = 'http://example.com/blog/'

        url_filter = DirectoryFilter()

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com'),
            record
        ))

        url_filter = DirectoryFilter(accepted=['/blog'])

        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com'),
            record
        ))

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            record
        ))

        url_filter = DirectoryFilter(rejected=['/cgi-bin/'])

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example.com/blog/'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example.com/cgi-bin'),
            record
        ))

    def test_backward_filename_filter(self):
        url_filter = BackwardFilenameFilter(
            accepted=['html', 'image.*.png'],
            rejected=['bmp', 'jp[eg]', 'image.123.png']
        )

        record = URLRecord()
        record.url = 'http://example.com/'

        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example/index.html'),
            record
        ))
        self.assertTrue(url_filter.test(
            URLInfo.parse('http://example/myimage.1003.png'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/myimage.123.png'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/blah.png'),
            record
        ))
        self.assertFalse(url_filter.test(
            URLInfo.parse('http://example/image.1003.png.bmp'),
            record
        ))
