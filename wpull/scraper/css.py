'''Stylesheet scraper.'''

import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.document.css import CSSReader
from wpull.document.util import detect_response_encoding
from wpull.scraper.base import BaseTextStreamScraper
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class CSSScraper(CSSReader, BaseTextStreamScraper):
    '''Scrapes CSS stylesheet documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def iter_processed_text(self, file, encoding=None, base_url=None):
        links = super().iter_processed_text(
            file, encoding=encoding, base_url=base_url)

        for text, is_link in links:
            if is_link and len(text) < 500:
                yield (text, is_link)
            elif not is_link:
                yield (text, False)


    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        inline_urls = set()
        base_url = request.url_info.url
        encoding = self._encoding_override or \
            detect_response_encoding(response)

        try:
            with wpull.util.reset_file_offset(response.body):
                for link in self.iter_processed_links(response.body, encoding,
                                                      base_url):
                    inline_urls.add(link)

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
