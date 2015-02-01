import unittest
from wpull.url import URLInfo
from wpull.urlrewrite import URLRewriter, strip_path_session_id, \
    strip_query_session_id


class TestURLRewrite(unittest.TestCase):
    def test_rewriter(self):
        rewriter = URLRewriter(hash_fragment=True, session_id=True)

        self.assertEquals(
            'http://example.com/',
            rewriter.rewrite(URLInfo.parse('http://example.com/')).url
        )
        self.assertEquals(
            'http://example.com/',
            rewriter.rewrite(URLInfo.parse('http://example.com/#hashtag!')).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse('https://groups.google.com/forum/#!forum/python-tulip')).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?stupid_hash_fragments&_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse(
                'https://groups.google.com/forum/?stupid_hash_fragments#!forum/python-tulip'
            )).url
        )
        self.assertEquals(
            'https://groups.google.com/forum/?stupid_hash_fragments=farts&_escaped_fragment_=forum/python-tulip',
            rewriter.rewrite(URLInfo.parse(
                'https://groups.google.com/forum/?stupid_hash_fragments=farts#!forum/python-tulip'
            )).url
        )

        self.assertEquals(
            'http://example.com/',
            rewriter.rewrite(URLInfo.parse(
                'http://example.com/?sid=0123456789abcdefghijklemopqrstuv'
            )).url
        )
        self.assertEquals(
            'http://example.com/?horse=dog&',
            rewriter.rewrite(URLInfo.parse(
                'http://example.com/?horse=dog&sid=0123456789abcdefghijklemopqrstuv'
            )).url
        )


    def test_strip_session_id_from_url_path(self):
        self.assertEqual(
            '/asdf',
            strip_path_session_id("/asdf"),
        )
        self.assertEqual(
            '/asdf/asdf.aspx',
            strip_path_session_id("/asdf/asdf.aspx"),
        )

        self.assertEqual(
            strip_path_session_id("/(S(4hqa0555fwsecu455xqckv45))/mileg.aspx"),
            '/mileg.aspx',
            'Check ASP_SESSIONID2'
        )

        self.assertEqual(
            strip_path_session_id("/(4hqa0555fwsecu455xqckv45)/mileg.aspx"),
            '/mileg.aspx',
            'Check ASP_SESSIONID2 (again)'
        )

        self.assertEqual(
            strip_path_session_id("/(a(4hqa0555fwsecu455xqckv45)S(4hqa0555fwsecu455xqckv45)f(4hqa0555fwsecu455xqckv45))/mileg.aspx?page=sessionschedules"),
            '/mileg.aspx?page=sessionschedules',
            'Check ASP_SESSIONID3'
        )

        self.assertEqual(
            strip_path_session_id("/photos/36050182@N05/"),
            '/photos/36050182@N05/',
            "'@' in path"
        )
    
    def test_strip_session_id_from_url_query(self):
        str32id = "0123456789abcdefghijklemopqrstuv"
        url = "jsessionid=" + str32id
        self.assertEqual(
            strip_query_session_id(url),
            ''
        )

        url = "jsessionid=" + str32id + '0'
        self.assertEqual(
            strip_query_session_id(url),
            'jsessionid=0123456789abcdefghijklemopqrstuv0',
            "Test that we don't strip if not 32 chars only."
        )

        url = "jsessionid=" + str32id + "&x=y"
        self.assertEqual(
            strip_query_session_id(url),
            'x=y',
            "Test what happens when followed by another key/value pair."
        )

        url = "one=two&jsessionid=" + str32id + "&x=y"
        self.assertEqual(
            strip_query_session_id(url),
            'one=two&x=y',
            "Test what happens when followed by another key/value pair and"
            "prefixed by a key/value pair."
        )

        url = "one=two&jsessionid=" + str32id
        self.assertEqual(
            strip_query_session_id(url),
            'one=two&',
            "Test what happens when prefixed by a key/value pair."
        )

        url = "aspsessionidABCDEFGH=" + "ABCDEFGHIJKLMNOPQRSTUVWX" + "&x=y"
        self.assertEqual(
            strip_query_session_id(url),
            'x=y',
            "Test aspsession."
        )

        url = "phpsessid=" + str32id + "&x=y"
        self.assertEqual(
            strip_query_session_id(url),
            'x=y',
            "Test archive phpsession."
        )

        url = "one=two&phpsessid=" + str32id + "&x=y"
        self.assertEqual(
            strip_query_session_id(url),
            'one=two&x=y',
            "With prefix too."
        )

        url = "one=two&phpsessid=" + str32id
        self.assertEqual(
            strip_query_session_id(url),
            'one=two&',
            "With only prefix"
        )

        url = "sid=9682993c8daa2c5497996114facdc805" + "&x=y";
        self.assertEqual(
            strip_query_session_id(url),
            'x=y',
            "Test sid."
        )

        url = "sid=9682993c8daa2c5497996114facdc805" + "&" + "jsessionid=" + str32id
        self.assertEqual(
            strip_query_session_id(url),
            '',
            "Igor test."
        )

        url = "CFID=1169580&CFTOKEN=48630702&dtstamp=22%2F08%2F2006%7C06%3A58%3A11"
        self.assertEqual(
            strip_query_session_id(url),
            'dtstamp=22%2F08%2F2006%7C06%3A58%3A11'
        )

        url = "CFID=12412453&CFTOKEN=15501799&dt=19_08_2006_22_39_28"
        self.assertEqual(
            strip_query_session_id(url),
            'dt=19_08_2006_22_39_28'
        )

        url = "CFID=14475712&CFTOKEN=2D89F5AF-3048-2957-DA4EE4B6B13661AB&r=468710288378&m=forgotten"
        self.assertEqual(
            strip_query_session_id(url),
            'r=468710288378&m=forgotten'
        )

        url = "CFID=16603925&CFTOKEN=2AE13EEE-3048-85B0-56CEDAAB0ACA44B8"
        self.assertEqual(
            strip_query_session_id(url),
            ''
        )

        url = "CFID=4308017&CFTOKEN=63914124&requestID=200608200458360%2E39414378"
        self.assertEqual(
            strip_query_session_id(url),
            'requestID=200608200458360%2E39414378'
        )
