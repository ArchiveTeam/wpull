# encoding=utf-8

import timeit

from wpull.backport.testing import unittest
from wpull.url import (URLInfo, schemes_similar, is_subdir, unquote,
    unquote_plus,
    quote, quote_plus, split_query, uppercase_percent_encoding, urljoin,
    flatten_path, is_likely_link, is_unlikely_link)


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
            'example.com',
            URLInfo.parse('http://example.com').hostname_with_port
        )
        self.assertEqual(
            'example.com',
            URLInfo.parse('https://example.com').hostname_with_port
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
            'example.com:8080',
            URLInfo.parse('example.com:8080').hostname_with_port
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

        # URL parsing is really different in each version of Python...
        self.assertRaises(ValueError, URLInfo.parse, '')
        self.assertRaises(ValueError, URLInfo.parse, '#')
        self.assertRaises(ValueError, URLInfo.parse, 'http://')
        self.assertRaises(ValueError, URLInfo.parse, 'example....com')
        self.assertRaises(ValueError, URLInfo.parse, 'http://example....com')
        self.assertRaises(ValueError, URLInfo.parse, 'http://example…com')
#         self.assertRaises(ValueError, URLInfo.parse, 'http://[34.4kf]::4')
        self.assertRaises(ValueError, URLInfo.parse, 'http://[34.4kf::4')
        self.assertRaises(ValueError, URLInfo.parse, 'http://dmn3]:3a:45')
        self.assertRaises(ValueError, URLInfo.parse, ':38/3')
        self.assertRaises(ValueError, URLInfo.parse, 'http://][a:@1]')
#         self.assertRaises(ValueError, URLInfo.parse, 'http://[[aa]]:4:]6')
        self.assertNotIn('[', URLInfo.parse('http://[a]').hostname)
        self.assertNotIn(']', URLInfo.parse('http://[a]').hostname)
        self.assertRaises(ValueError, URLInfo.parse, 'http://[[a]')
        self.assertRaises(ValueError, URLInfo.parse, 'http://[[a]]a]')
        self.assertRaises(ValueError, URLInfo.parse, 'http://[[a:a]]')

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
            'www.xn--hda.com',
            URLInfo.parse('www.xn--hda.com/asdf').hostname
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
                '?blah=http://example.com/?fail=true',
            URLInfo.parse(
                'http://example.com/'
                    '?blah=http%3A%2F%2Fexample.com%2F%3Ffail%3Dtrue').url
        )
        self.assertEqual(
            'http://example.com/'
                '?blah=http://example.com/?fail=true',
            URLInfo.parse(
                'http://example.com/'
                    '?blah=http://example.com/?fail%3Dtrue').url
        )

        self.assertEqual(
            'http://example.com/??blah=blah[0:]=blah?blah%22&d%26_',
            URLInfo.parse(
                'http://example.com/??blah=blah[0:]=bl%61h?blah"&d%26_').url
        )

        self.assertEqual(
            'http://example.com/',
            URLInfo.parse('http://example.com/../').url
        )
        self.assertEqual(
            'http://example.com/index.html',
            URLInfo.parse('http://example.com/../index.html').url
        )
        self.assertEqual(
            'http://example.com/b/style.css',
            URLInfo.parse('http://example.com/a/../../b/style.css').url
        )
        self.assertEqual(
            'http://example.com/a/style.css',
            URLInfo.parse('http://example.com/a/b/../style.css').url
        )
        self.assertEqual(
            'http://example.com/@49IMG.DLL/$SESSION$/image.png;large',
            URLInfo.parse(
                'http://example.com/@49IMG.DLL/$SESSION$/image.png;large').url
        )
        self.assertEqual(
            'http://example.com/@49IMG.DLL/$SESSION$/imag%C3%A9.png;large',
            URLInfo.parse(
                'http://example.com/@49IMG.DLL/$SESSION$/imagé.png;large').url
        )
        self.assertEqual(
            'http://example.com/$c/%25system.exe/',
            URLInfo.parse('http://example.com/$c/%system.exe/').url
        )

        self.assertEqual(
            'http://example.com/?a',
            URLInfo.parse('http://example.com?a').url
        )
        self.assertEqual(
            'http://example.com/?a=',
            URLInfo.parse('http://example.com?a=').url
        )
        self.assertEqual(
            'http://example.com/?a=1',
            URLInfo.parse('http://example.com?a=1').url
        )
        self.assertEqual(
            'http://example.com/?a=1&b',
            URLInfo.parse('http://example.com?a=1&b').url
        )
        self.assertEqual(
            'http://example.com/?a=1&b=',
            URLInfo.parse('http://example.com?a=1&b=').url
        )
        self.assertEqual(
            'https://[2001:db8:85a3:8d3:1319:8a2e:370:7348]:8080/ipv6',
            URLInfo.parse(
                'https://[2001:db8:85a3:8d3:1319:8a2e:370:7348]:8080/ipv6'
            ).url
        )
        self.assertEqual(
            'http://[2001:db8:85a3:8d3:1319:8a2e:370:7348]/ipv6',
            URLInfo.parse(
                'http://[2001:db8:85a3:8d3:1319:8a2e:370:7348]/ipv6'
            ).url
        )

    def test_url_info_round_trip(self):
        urls = [
            'http://example.com/blah%20blah/',
            'example.com:81?blah=%c3%B0',
            'http://example.com/a/../../b/style.css',
            'http://example.com/'
                '?blah=http%3A%2F%2Fexample.com%2F%3Ffail%3Dtrue',
            'http://example.com/??blah=blah[0:]=bl%61h?blah"&d%26_',
            'http://[2001:db8:85a3:8d3:1319:8a2e:370:7348]/ipv6',
        ]

        for url in urls:
            URLInfo.parse(URLInfo.parse(url).url)

    @unittest.skip('TODO: implement these')
    def test_ip_address_normalization(self):
        self.assertEqual(
            'http://192.0.2.235/',
            URLInfo.parse('https://0xC0.0x00.0x02.0xEB').url
        )
        self.assertEqual(
            'http://192.0.2.235/',
            URLInfo.parse('https://0301.1680.0002.0353').url
        )
        self.assertEqual(
            'http://192.0.2.235/',
            URLInfo.parse('https://0xC00002EB/').url
        )
        self.assertEqual(
            'http://192.0.2.235/',
            URLInfo.parse('https://3221226219/').url
        )
        self.assertEqual(
            'http://192.0.2.235/',
            URLInfo.parse('https://030000001353/').url
        )
        self.assertEqual(
            'https://[2001:db8:85a3:8d3:1319:8a2e:370:7348]:8080/ipv6',
            URLInfo.parse(
                'https://[2001:db8:85a3:8d3:1319:8a2e:370:7348]:8080/ipv6'
            ).url
        )
        self.assertEqual(
            'https://[::1]/',
            URLInfo.parse('https://[0:0:0:0:0:0:0:1]').url
        )
        self.assertEqual(
            'https://[::ffff:192.0.2.128]/',
            URLInfo.parse('https://[::ffff:c000:0280]').url
        )

    @unittest.skip('experiment only')
    def test_url_info_timing(self):
        t1 = timeit.timeit(
            '''URLInfo.parse(
            "http://asdjfklðkjir.com:585?" +
            "$fasjdfklfd=45asdfasdf345hd.s&g4=4d&&" +
            str(random.randint(0,1000))
            )''',
            number=2000,
            setup='import random; from wpull.url import URLInfo',
        )
        t2 = timeit.timeit(
            '''URLInfo.parse(
            "http://asdjfklðkjir.com:585?" +
            "$fasjdfklfd=45asdfasdf345hd.s&g4=4d&&" +
            str(random.randint(0,1000))
            , use_cache=False
            )''',
            number=2000,
            setup='import random; from wpull.url import URLInfo',
        )
        print(t1, t2)
        self.assertLess(t1, t2)

    def test_url_info_to_dict(self):
        url_info = URLInfo.parse('https://example.com/file.jpg')
        url_info_dict = url_info.to_dict()
        self.assertEqual('/file.jpg', url_info_dict['path'])
        self.assertEqual('example.com', url_info_dict['hostname'])
        self.assertEqual('https', url_info_dict['scheme'])
        self.assertEqual(443, url_info_dict['port'])
        self.assertEqual('utf-8', url_info_dict['encoding'])



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
        self.assertEqual(
            'http://example.com/a/style.css',
            urljoin('http://example.com/a/', './style.css')
        )
        self.assertEqual(
            'http://example.com/style.css',
            urljoin('http://example.com/a/', './../style.css')
        )

    def test_flatten_path(self):
        self.assertEqual('/', flatten_path('/'))
        self.assertEqual('/', flatten_path('/../../../'))
        self.assertEqual('/', flatten_path('/.././'))
        self.assertEqual('/a', flatten_path('/../a/../a'))
        self.assertEqual('/a/', flatten_path('/../a/../a/'))
        self.assertEqual('//a/a/', flatten_path('//a//../a/'))
        self.assertEqual('/index.html', flatten_path('/./index.html'))
        self.assertEqual('/index.html', flatten_path('/../index.html'))
        self.assertEqual('/a/index.html', flatten_path('/a/./index.html'))
        self.assertEqual('/index.html', flatten_path('/a/../index.html'))
        self.assertEqual('/doc/index.html', flatten_path('/../doc/index.html'))
        self.assertEqual(
            '/dog/doc/index.html',
            flatten_path('/dog/cat/../doc/index.html')
        )
        self.assertEqual(
            '/dog/doc/index.html',
            flatten_path('/dog/../dog/./cat/../doc/././../doc/index.html')
        )

    def test_is_likely_link(self):
        self.assertTrue(is_likely_link('image.png'))
        self.assertTrue(is_likely_link('video.mp4'))
        self.assertTrue(is_likely_link('/directory'))
        self.assertTrue(is_likely_link('directory/'))
        self.assertTrue(is_likely_link('/directory/'))
        self.assertTrue(is_likely_link('../directory/'))
        self.assertTrue(is_likely_link('http://example.com/'))
        self.assertTrue(is_likely_link('https://example.com/'))
        self.assertTrue(is_likely_link('ftp://example.com'))
        self.assertTrue(is_likely_link('directory/index.html'))
        self.assertFalse(is_likely_link('directory/another_directory'))
        self.assertTrue(is_likely_link('application/windows.exe'))
        self.assertTrue(is_likely_link('//example.com/admin'))
        self.assertFalse(is_likely_link('12.0'))
        self.assertFalse(is_likely_link('7'))
        self.assertFalse(is_likely_link('horse'))
        self.assertFalse(is_likely_link(''))
        self.assertFalse(is_likely_link('setTimeout(myTimer, 1000)'))
        self.assertFalse(is_likely_link('comment.delete'))
        self.assertFalse(is_likely_link('example.com'))
        self.assertFalse(is_likely_link('example.net'))
        self.assertFalse(is_likely_link('example.org'))
        self.assertFalse(is_likely_link('example.edu'))

    def test_is_unlikely_link(self):
        self.assertTrue(is_unlikely_link('example.com+'))
        self.assertTrue(is_unlikely_link('www.'))
        self.assertTrue(is_unlikely_link(':example.com'))
        self.assertTrue(is_unlikely_link(',example.com'))
        self.assertTrue(is_unlikely_link('http:'))
        self.assertTrue(is_unlikely_link('.example.com'))
        self.assertTrue(is_unlikely_link('doc[0]'))
        self.assertTrue(is_unlikely_link('/'))
        self.assertTrue(is_unlikely_link('//'))
        self.assertTrue(is_unlikely_link('application/json'))
        self.assertTrue(is_unlikely_link('application/javascript'))
        self.assertTrue(is_unlikely_link('text/javascript'))
        self.assertTrue(is_unlikely_link('text/plain'))
        self.assertFalse(is_unlikely_link('http://'))
        self.assertFalse(is_unlikely_link('example'))
        self.assertFalse(is_unlikely_link('example.com'))
        self.assertFalse(is_unlikely_link('//example.com/assets/image.css'))
        self.assertFalse(is_unlikely_link('./image.css'))
        self.assertFalse(is_unlikely_link('../image.css'))
