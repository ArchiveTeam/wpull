'''Javascript scraper.'''

import gettext
import json
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.document.javascript import JavaScriptReader
from wpull.document.util import detect_response_encoding
from wpull.scraper.base import BaseTextStreamScraper
from wpull.scraper.util import is_likely_inline, is_likely_link, \
    is_unlikely_link
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class JavaScriptScraper(JavaScriptReader, BaseTextStreamScraper):
    '''Scrapes JavaScript documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def iter_text(self, file, encoding=None):
        for text, match in super().iter_text(file, encoding):
            if match:
                try:
                    new_text = json.loads('"{0}"'.format(text))
                except ValueError:
                    yield (text, match)
                else:
                    if is_likely_link(new_text) and \
                            not is_unlikely_link(new_text):
                        yield (new_text, match)
                    else:
                        yield (text, None)
            else:
                yield (text, None)

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        inline_urls = set()
        linked_urls = set()
        base_url = request.url_info.url
        encoding = self._encoding_override or \
            detect_response_encoding(response)

        try:
            with wpull.util.reset_file_offset(response.body):
                for link in self.iter_processed_links(response.body, encoding,
                                                      base_url):
                    if is_likely_inline(link):
                        inline_urls.add(link)
                    else:
                        linked_urls.add(link)

        except UnicodeError as error:
            _logger.warning(__(
                _('Failed to read document at ‘{url}’: {error}'),
                url=request.url_info.url, error=error
            ))

        return {
            'inline_urls': inline_urls,
            'linked_urls': linked_urls,
            'encoding': encoding,
        }
