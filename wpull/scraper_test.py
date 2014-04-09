# encoding=utf-8
import os.path
import shutil

from wpull.backport.testing import unittest
from wpull.http.request import Request, Response
from wpull.scraper import (HTMLScraper, CSSScraper, clean_link_soup,
    SitemapScraper)
import wpull.util


class TestDocument(unittest.TestCase):
    def test_html_scraper_links(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, 'OK')
        response.fields['Refresh'] = '3; url=header_refresh.html'

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'many_urls.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual('ascii', scrape_info['encoding'])

        self.assertEqual({
            'http://example.com/style_import_url.css',
            'http://example.com/style_import_quote_url.css',
            'http://example.com/style_single_quote_import.css',
            'http://example.com/style_double_quote_import.css',
            'http://example.com/link_href.css',
            'http://example.com/script.js',
            'http://example.com/body_background.png',
            'http://example.com/images/table_background.png',
            'http://example.com/images/td_background.png',
            'http://example.com/images/th_background.png',
            'http://example.com/style_url1.png',
            'http://example.com/style_url2.png',
            'http://example.com/applet/',  # returned by lxml
            'http://example.com/applet/applet_code.class',
            'http://example.com/applet/applet_src.class',
            'http://example.com/bgsound.mid',
            'http://example.com/audio_src.wav',
            'http://example.net/source_src.wav',
            'http://example.com/embed_src.mov',
            'http://example.com/fig_src.png',
            'http://example.com/frame_src.html',
            'http://example.com/iframe_src.html',
            'http://example.com/img_href.png',
            'http://example.com/img_lowsrc.png',
            'http://example.com/img_src.png',
            'http://example.com/input_src.png',
            'http://example.com/layer_src.png',
            'http://example.com/object/',  # returned by lxml
            'http://example.com/object/object_data.swf',
            'http://example.com/object/object_archive.dat',
            'http://example.com/overlay_src.html',
            },
            inline_urls
        )
        self.assertEqual({
            'http://example.net/soup.html',
            'http://example.com/a_href.html',
            'http://example.com/area_href.html',
            'http://example.com/frame_src.html',
            'http://example.com/embed_href.html',
            'http://example.com/embed_src.mov',
            'http://example.com/form_action.html',
            'http://example.com/iframe_src.html',
            'http://example.com/layer_src.png',
            'http://example.com/overlay_src.html',
            'ftp://ftp.protocol.invalid/',
            'mailto:user@example.com',
            'http://a-double-slash.example',
            'http://example.com/header_refresh.html',
            'https://[2001:db8:85a3:8d3:1319:8a2e:370:7348]:8080/ipv6',
            },
            linked_urls
        )

        for url in inline_urls | linked_urls:
            self.assertIsInstance(url, str)

    def test_html_soup(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'soup.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual(
            {'http://example.com/ABOUTM~1.JPG'},
            inline_urls
        )
        self.assertEqual(
            {
                'http://example.com/BLOG',
                'http://example.com/web ring/Join.htm',
            },
            linked_urls
        )

    def test_html_early_end_html_soup(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'Download.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual(
            {
                'http://igrosale.com/templates/default/css/main.css',
                'http://igrosale.com/templates/default/css/dcaccordion.css',
                'http://igrosale.com/templates/default/css/graphite.css',
                'http://igrosale.com/templates/default/pix/fon_header.png',
                'http://example.com/icons/blank.gif',
                'http://example.com/icons/back.gif',
                'http://example.com/icons/folder.gif',
                'http://example.com/icons/unknown.gif',
                'http://example.com/icons/layout.gif',
                'http://example.com/icons/layout.gif',
            },
            inline_urls
        )
        self.assertEqual(
            {
                'http://igrosale.com',
                'http://example.com/',
                'http://example.com/?C=N;O=D',
                'http://example.com/?C=M;O=A',
                'http://example.com/?C=S;O=A',
                'http://example.com/Igrosoft/',
                'http://example.com/Novomatic/',
                'http://example.com/Original%20Resources/',
                'http://example.com/Photo/',
                'http://example.com/SIMM%20Flash%20Programmer/',
                'http://example.com/Belatra%20GAL.rar',
                'http://example.com/Bill%20Acceptor%20ICT%20Pulse%20(Rus).pdf',
                'http://example.com/DGIEditor%203.0.1.512.rar',
                'http://example.com/'
                    'Driver%20Sapphire%20Serial%20Ports%20Adapter.rar',
                'http://example.com/'
                    'Igrosoft%20MAME%20Full%20+%20Source%20Code.rar',
                'http://example.com/JP103.rar',
                'http://example.com/KP%205-6%20v1.rar',
                'http://example.com/UX9%20Technical%20Specification.pdf',
                'http://example.com/'
                    'Windows%20XP%20Professional%20SP3%20x86%20VL%20Rus.rar',
            },
            linked_urls
        )

    def test_html_mojibake(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html; charset=Shift_JIS'

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'mojibake.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual('shift_jis', scrape_info['encoding'])

        self.assertEqual(
            set(),
            inline_urls
        )
        self.assertEqual(
            {'http://example.com/文字化け'},
            linked_urls
        )

    def test_html_krokozyabry(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html; charset=KOI8-R'

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'krokozyabry.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual('koi8-r', scrape_info['encoding'])

        self.assertEqual(
            set(),
            inline_urls
        )
        self.assertEqual(
            {'http://example.com/Кракозябры'},
            linked_urls
        )

    def test_html_wrong_charset(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'kcna.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual('utf-16-le', scrape_info['encoding'])

        self.assertEqual(
            {
                'http://example.com/utm/__utm.js',
                'http://example.com/Knewskage.gif',
                'http://example.com/Lline.gif',
                'http://example.com/Sline.gif',
                'http://example.com/korean01.gif',
                'http://example.com/english01.gif',
            },
            inline_urls
        )
        self.assertEqual(
            {
                'http://example.com/index-k.htm',
                'http://example.com/index-e.htm'
            },
            linked_urls
        )

    def test_html_not_quite_charset(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'videogame_top.htm')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertIn(
            'http://example.com/copyright_2001_2006_rtype.gif',
            inline_urls
        )
        self.assertIn(
            'http://www.geocities.jp/gamehouse_grindcrusher/',
            linked_urls
        )

    def test_html_garbage(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html'

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'\x01\x00\x01\x00l~Z\xff\x0f`y\x80\x00p<\x7f'
                b'\xffndo\xff\xff-\x83{d\xec</\xfe\x80\x00\xb4Bo'
                b'\x7f\xff\xff\xffV\xc1\xff\x7f\xff7'
            )

        scrape_info = scraper.scrape(request, response)

        self.assertTrue(scrape_info)

    def test_html_encoding_lxml_name_mismatch(self):
        '''It should accept encoding names with underscore.'''
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html; charset=EUC_KR'

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                '<html><body>힖'.encode('euc_kr')
            )

        scrape_info = scraper.scrape(request, response)

        self.assertTrue(scrape_info)
        self.assertEqual('euc_kr', scrape_info['encoding'])

    def test_html_serious_bad_encoding(self):
        scraper = HTMLScraper(encoding_override='utf8')
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html; charset=utf8'

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'xkcd_1_evil.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)

        self.assertFalse(scrape_info)

    def test_html_emptyness(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, '')
        response.fields['content-type'] = 'text/html'

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'OK'
            )

        scrape_info = scraper.scrape(request, response)

        self.assertFalse(scrape_info)

    def test_scrape_css_urls(self):
        text = '''
        @import url("fineprint.css") print;
        @import url("bluish.css") projection, tv;
        @import 'custom.css';
        @import url("chrome://communicator/skin/");
        @import "common.css" screen, projection;
        @import url('landscape.css') screen and (orientation:landscape);
        @import url(cool.css);
        @import warm.css;
        '''

        urls = set(CSSScraper.scrape_urls(text))

        self.assertEqual({
            'fineprint.css',
            'bluish.css',
            'chrome://communicator/skin/',
            'landscape.css',
            'cool.css'
            },
            urls
        )

        urls = set(CSSScraper.scrape_imports(text))

        self.assertEqual({
            'fineprint.css',
            'bluish.css',
            'custom.css',
            'chrome://communicator/skin/',
            'common.css',
            'landscape.css',
            'cool.css',
            'warm.css',
            },
            urls
        )

    def test_css_scraper_links(self):
        scraper = CSSScraper()
        request = Request.new('http://example.com/styles.css')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'styles.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://example.com/mobile.css',
            'http://example.com/images/star.gif',
            },
            inline_urls
        )
        self.assertFalse(linked_urls)

    def test_css_scraper_mojibake(self):
        scraper = CSSScraper()
        request = Request.new('http://example.com/styles.css')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'mojibake.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://example.com/文字化け.png',
            },
            inline_urls
        )
        self.assertFalse(linked_urls)

    def test_css_scraper_krokozyabry(self):
        scraper = CSSScraper()
        request = Request.new('http://example.com/styles.css')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'krokozyabry.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://example.com/Кракозябры.png',
            },
            inline_urls
        )
        self.assertFalse(linked_urls)

    def test_sitemap_scraper_robots(self):
        scraper = SitemapScraper()
        request = Request.new('http://example.com/robots.txt')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'Sitemap: http://example.com/sitemap00.xml'
            )

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://example.com/sitemap00.xml',
            },
            linked_urls
        )
        self.assertFalse(inline_urls)

    def test_sitemap_scraper_invalid_robots(self):
        scraper = SitemapScraper()
        request = Request.new('http://example.com/robots.txt')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'dsfju3wrji kjasSItemapsdmjfkl wekie;er :Ads fkj3m /Dk'
            )

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertFalse(linked_urls)
        self.assertFalse(inline_urls)

    def test_sitemap_scraper_xml_index(self):
        scraper = SitemapScraper()
        request = Request.new('http://example.com/sitemap.xml')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'''<?xml version="1.0" encoding="UTF-8"?>
                <sitemapindex
                xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                   <sitemap>
                      <loc>http://www.example.com/sitemap1.xml.gz</loc>
                      <lastmod>2004-10-01T18:23:17+00:00</lastmod>
                   </sitemap>
                </sitemapindex>
            '''
            )

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://www.example.com/sitemap1.xml.gz',
            },
            linked_urls
        )
        self.assertFalse(inline_urls)

    def test_sitemap_scraper_xml(self):
        scraper = SitemapScraper()
        request = Request.new('http://example.com/sitemap.xml')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'''<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                   <url>
                      <loc>http://www.example.com/</loc>
                      <lastmod>2005-01-01</lastmod>
                      <changefreq>monthly</changefreq>
                      <priority>0.8</priority>
                   </url>
                </urlset>
            '''
            )

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual({
            'http://www.example.com/',
            },
            linked_urls
        )
        self.assertFalse(inline_urls)

    def test_sitemap_scraper_invalid_xml(self):
        scraper = SitemapScraper()
        request = Request.new('http://example.com/sitemap.xml')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(
                b'''<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                   <url>
                      <loc>http://www.example.com/</loc>
            '''
            )

        scrape_info = scraper.scrape(request, response)
        self.assertFalse(scrape_info)

    def test_clean_link_soup(self):
        self.assertEqual(
            'http://example.com',
            clean_link_soup('http://example.com  ')
        )
        self.assertEqual(
            'http://example.com/',
            clean_link_soup('\n\r\thttp://example.com\n\r\r\r\n\t/')
        )
        self.assertEqual(
            'http://example.com/ something',
            clean_link_soup('http://example.com\n\t / something  \n\r\t')
        )
        self.assertEqual(
            'http://example.com/dog cat/',
            clean_link_soup('http://example.com/\n dog \tcat\r/\n')
        )
        self.assertEqual(
            'ßðf ¤Jáßðff ßðfœ³²œ¤ œë ßfœ',
            clean_link_soup('ß\tðf ¤Jáßðf\n f ßðfœ³²œ¤ œë ßfœ ')
        )
