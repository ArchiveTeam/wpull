# encoding=utf-8
import os.path
import shutil

from wpull.backport.testing import unittest
from wpull.scraper import HTMLScraper, CSSScraper
from wpull.http import Request, Response
import wpull.util


class TestDocument(unittest.TestCase):
    def test_html_scraper_links(self):
        scraper = HTMLScraper()
        request = Request.new('http://example.com/')
        response = Response('HTTP/1.0', 200, 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            html_file_path = os.path.join(os.path.dirname(__file__),
                'testing', 'samples', 'many_urls.html')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body.content_file)

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertEqual('UTF-8', scrape_info['encoding'])

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
            {'http://example.com/BLOG'},
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

        self.assertIsNone(scrape_info)

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
