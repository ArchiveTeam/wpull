import unittest

from wpull.body import Body
from wpull.document.htmlparse.html5lib_ import HTMLParser as HTML5LibHTMLParser
from wpull.http.request import Request, Response
from wpull.scraper.sitemap import SitemapScraper
from wpull.util import IS_PYPY
import wpull.util


if not IS_PYPY:
    from wpull.document.htmlparse.lxml_ import HTMLParser as LxmlHTMLParser
else:
    LxmlHTMLParser = type(NotImplemented)


class Mixin(object):
    def get_html_parser(self):
        raise NotImplementedError()

    def test_sitemap_scraper_robots(self):
        scraper = SitemapScraper(self.get_html_parser())
        request = Request('http://example.com/robots.txt')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            response.body.write(
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
        scraper = SitemapScraper(self.get_html_parser())
        request = Request('http://example.com/robots.txt')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            response.body.write(
                b'dsfju3wrji kjasSItemapsdmjfkl wekie;er :Ads fkj3m /Dk'
            )

        scrape_info = scraper.scrape(request, response)
        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']

        self.assertFalse(linked_urls)
        self.assertFalse(inline_urls)

    def test_sitemap_scraper_xml_index(self):
        scraper = SitemapScraper(self.get_html_parser())
        request = Request('http://example.com/sitemap.xml')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            response.body.write(
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
        scraper = SitemapScraper(self.get_html_parser())
        request = Request('http://example.com/sitemap.xml')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            response.body.write(
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
        scraper = SitemapScraper(self.get_html_parser())
        request = Request('http://example.com/sitemap.xml')
        response = Response(200, 'OK')
        response.body = Body()

        with wpull.util.reset_file_offset(response.body):
            response.body.write(
                b'''<?xml version="1.0" encoding="UTF-8"?>
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                   <url>
                      <loc>http://www.example.com/</loc>
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


@unittest.skipIf(IS_PYPY, 'Not supported under PyPy')
class TestLxmlSitemap(Mixin, unittest.TestCase):
    def get_html_parser(self):
        return LxmlHTMLParser()


class TestHTML5LibSitemap(Mixin, unittest.TestCase):
    def get_html_parser(self):
        return HTML5LibHTMLParser()
