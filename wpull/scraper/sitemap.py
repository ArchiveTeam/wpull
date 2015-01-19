'''Sitemap scraper'''
import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.document.sitemap import SitemapReader
from wpull.document.util import detect_response_encoding
from wpull.item import LinkType
import wpull.util
from wpull.scraper.base import BaseExtractiveScraper, LinkContext, ScrapeResult


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class SitemapScraper(SitemapReader, BaseExtractiveScraper):
    '''Scrape Sitemaps'''
    def __init__(self, html_parser, encoding_override=None):
        super().__init__(html_parser)
        self._encoding_override = encoding_override

    def scrape(self, request, response, link_type=None):
        if not self.is_supported(request=request, response=response):
            return
        if link_type and link_type != LinkType.sitemap:
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)
        link_contexts = set()

        try:
            with wpull.util.reset_file_offset(response.body):
                link_iter = self.iter_processed_links(response.body, encoding,
                                                      base_url)
                for link in link_iter:
                    link_contexts.add(LinkContext(link, linked=True))

        except (UnicodeError, self._html_parser.parser_error) as error:
            _logger.warning(__(
                _('Failed to read document at ‘{url}’: {error}'),
                url=request.url_info.url, error=error
            ))

        return ScrapeResult(link_contexts, encoding)
