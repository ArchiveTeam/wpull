'''Javascript scraper.'''

import gettext
import json
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.document.javascript import JavaScriptReader
from wpull.document.util import detect_response_encoding
from wpull.item import LinkType
from wpull.scraper.base import BaseTextStreamScraper, LinkContext, ScrapeResult
from wpull.scraper.util import is_likely_inline, is_likely_link, \
    is_unlikely_link, urljoin_safe
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class JavaScriptScraper(JavaScriptReader, BaseTextStreamScraper):
    '''Scrapes JavaScript documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def iter_processed_text(self, file, encoding=None, base_url=None):
        for text, is_link in self.iter_text(file, encoding):
            if is_link:
                try:
                    new_text = json.loads('"{0}"'.format(text))
                except ValueError:
                    yield (text, False)
                    continue

                if is_unlikely_link(new_text) or not is_likely_link(new_text):
                    yield (text, False)
                    continue

                if base_url:
                    new_link = urljoin_safe(base_url, new_text,
                                            allow_fragments=False)
                else:
                    new_link = new_text

                if new_link:
                    yield (new_link, True)
                else:
                    yield (text, False)
            else:
                yield (text, False)

    def scrape(self, request, response, link_type=None):
        if not self.is_supported(request=request, response=response):
            return
        if link_type and link_type != LinkType.javascript:
            return

        link_contexts = set()
        base_url = request.url_info.url
        encoding = self._encoding_override or \
            detect_response_encoding(response)

        try:
            with wpull.util.reset_file_offset(response.body):
                for link in self.iter_processed_links(response.body, encoding,
                                                      base_url):
                    inline = is_likely_inline(link)
                    link_contexts.add(
                        LinkContext(link, inline=inline, linked=not inline)
                    )

        except UnicodeError as error:
            _logger.warning(__(
                _('Failed to read document at ‘{url}’: {error}'),
                url=request.url_info.url, error=error
            ))

        return ScrapeResult(link_contexts, encoding)
