'''Stylesheet scraper.'''

import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.document.css import CSSReader
from wpull.document.util import detect_response_encoding
from wpull.scraper.base import BaseDocumentScraper, ScrapedLinkResult
from wpull.scraper.util import urljoin_safe
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class CSSScraper(CSSReader, BaseDocumentScraper):
    '''Scrapes CSS stylesheet documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        scraped_links = self.iter_scrape(request, response)
        inline_urls = set()
        encoding = 'latin1'

        try:
            for scraped_link in scraped_links:
                encoding = scraped_link.encoding
                inline_urls.add(scraped_link.link)

        except UnicodeError as error:
            _logger.warning(__(
                _('Failed to read document at ‘{url}’: {error}'),
                url=request.url_info.url, error=error
            ))

        return {
            'inline_urls': inline_urls,
            'linked_urls': (),
            'encoding': encoding,
        }

    def iter_scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)

        with wpull.util.reset_file_offset(response.body):
            for link in self.read_links(response.body, encoding):
                link = urljoin_safe(base_url, link, allow_fragments=False)

                if link:
                    yield ScrapedLinkResult(link, True, encoding)
