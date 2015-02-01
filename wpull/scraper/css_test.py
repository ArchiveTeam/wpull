import os.path
import shutil
import unittest

from wpull.body import Body
from wpull.http.request import Request, Response
from wpull.item import LinkType
from wpull.scraper.css import CSSScraper
import wpull.util

ROOT_PATH = os.path.join(os.path.dirname(__file__), '..')


class TestCSS(unittest.TestCase):
    def test_scrape_import_urls(self):
        text = '''
        @import url("fineprint.css") print;
        @import url("bluish.css") projection, tv;
        @import 'custom.css';
        @import url("chrome://communicator/skin/");
        @import "common.css" screen, projection;
        @import url('landscape.css') screen and (orientation:landscape);
        @import url(cool.css);
        @import warm.css;
        ''' + '@import url("' + ('a' * 1000) + '");'

        urls = set(CSSScraper().scrape_links(text))

        self.assertEqual({
            'fineprint.css',
            'bluish.css',
            'chrome://communicator/skin/',
            'landscape.css',
            'cool.css',
            'custom.css',
            'common.css',
            'warm.css',
        },
            urls
        )

    def test_css_scraper_links(self):
        scraper = CSSScraper()
        request = Request('http://example.com/styles.css')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            html_file_path = os.path.join(ROOT_PATH,
                                          'testing', 'samples', 'styles.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body)

        scrape_result = scraper.scrape(request, response)
        inline_urls = scrape_result.inline_links
        linked_urls = scrape_result.linked_links

        self.assertEqual({
            'http://example.com/mobile.css',
            'http://example.com/images/star.gif',
        },
            inline_urls
        )
        self.assertFalse(linked_urls)

    def test_css_scraper_reject_type(self):
        scraper = CSSScraper()
        request = Request('http://example.com/styles.css')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            html_file_path = os.path.join(ROOT_PATH,
                                          'testing', 'samples', 'styles.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body)

        scrape_result = scraper.scrape(request, response,
                                       link_type=LinkType.html)
        self.assertFalse(scrape_result)

    def test_css_scraper_mojibake(self):
        scraper = CSSScraper()
        request = Request('http://example.com/styles.css')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            html_file_path = os.path.join(ROOT_PATH,
                                          'testing', 'samples', 'mojibake.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body)

        scrape_result = scraper.scrape(request, response)
        inline_urls = scrape_result.inline_links
        linked_urls = scrape_result.linked_links

        self.assertEqual({
            'http://example.com/文字化け.png',
        },
            inline_urls
        )
        self.assertFalse(linked_urls)

    def test_css_scraper_krokozyabry(self):
        scraper = CSSScraper()
        request = Request('http://example.com/styles.css')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            html_file_path = os.path.join(ROOT_PATH,
                                          'testing', 'samples',
                                          'krokozyabry.css')
            with open(html_file_path, 'rb') as in_file:
                shutil.copyfileobj(in_file, response.body)

        scrape_result = scraper.scrape(request, response)
        inline_urls = scrape_result.inline_links
        linked_urls = scrape_result.linked_links

        self.assertEqual({
            'http://example.com/Кракозябры.png',
        },
            inline_urls
        )
        self.assertFalse(linked_urls)
