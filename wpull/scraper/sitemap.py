'''Sitemap scraper'''
import gettext
import logging

import lxml.etree

from wpull.backport.logging import BraceMessage as __
from wpull.document.sitemap import SitemapReader
from wpull.document.util import detect_response_encoding
from wpull.scraper.base import BaseDocumentScraper
from wpull.scraper.util import urljoin_safe, clean_link_soup
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class SitemapScraper(SitemapReader, BaseDocumentScraper):
    '''Scrape Sitemaps'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)
        links = set()

        try:
            with wpull.util.reset_file_offset(response.body):
                link_iter = self.read_links(
                    response.body, encoding=encoding
                )

                for link in link_iter:
                    link = urljoin_safe(
                        base_url,
                        clean_link_soup(link)
                    )

                    if link:
                        links.add(link)

        except (UnicodeError, lxml.etree.LxmlError) as error:
            _logger.warning(__(
                _('Failed to read document at ‘{url}’: {error}'),
                url=request.url_info.url, error=error
            ))

        return {
            'inline_urls': (),
            'linked_urls': links,
            'encoding': encoding
        }
