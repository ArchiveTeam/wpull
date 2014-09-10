'''Base classes'''
import abc
import collections
import io

from wpull.document.base import BaseTextStreamReader, \
    BaseHTMLReader, BaseExtractiveReader
from wpull.scraper.util import urljoin_safe


ScrapedLinkResult = collections.namedtuple(
    'ScrapedLinkResultType',
    ['link', 'inline', 'encoding']
)
'''A named tuple decribing a scraped link.

Attributes:
    link (str): The link that was scraped.
    inline (bool): Whether the link is an embeded object.
    encoding (str): The character encoding of the link.
'''


class BaseScraper(object):
    '''Base class for scrapers.'''
    @abc.abstractmethod
    def scrape(self, request, response):
        '''Extract the URLs from the document.

        Args:
            request (:class:`.http.request.Request`): The request.
            response (:class:`http.request.Response`): The response.

        Returns:
            dict, None: Returns a dict or None.

            If a dict is provided, the mandatory values are:

                * ``inline_urls``: URLs of objects embedded in the document
                * ``linked_urls``': URLs of objects linked from the document
                *  ``encoding``: the character encoding of the document

            If None, then the scraper does not support scraping the document.
        '''


class BaseTextStreamScraper(BaseScraper, BaseTextStreamReader):
    '''Base class for scrapers that process either link and non-link text.'''
    def iter_processed_text(self, file, encoding=None, base_url=None):
        '''Return the file text and processed absolute links.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.
            base_url (str): The URL at which the document is located.

        Returns:
            iterator: Each item is a tuple:

            1. str: The text
            2. bool: Whether the text a link
        '''
        for text, is_link in self.iter_text(file, encoding):
            if is_link and base_url:
                new_link = urljoin_safe(base_url, text, allow_fragments=False)

                if new_link:
                    yield (new_link, True)
                else:
                    yield (new_link, False)
            else:
                yield (text, is_link)

    def iter_processed_links(self, file, encoding=None, base_url=None):
        '''Return the links.

        This function is a convenience function for calling
        :meth:`iter_processed_text` and returning only the links.
        '''
        return [item[0] for item in self.iter_processed_text(file, encoding, base_url) if item[1]]

    def scrape_links(self, text):
        '''Convenience function for scraping from a text string.'''
        return self.iter_processed_links(io.StringIO(text))


class BaseExtractiveScraper(BaseScraper, BaseExtractiveReader):
    def iter_processed_links(self, file, encoding=None, base_url=None):
        '''Return the links.

        Returns:
            iterator: Each item is a str which represents a link.
        '''
        for link in self.iter_links(file, encoding):
            new_link = urljoin_safe(base_url, link, allow_fragments=False)
            if new_link:
                yield new_link


class BaseHTMLScraper(BaseScraper, BaseHTMLReader):
    pass


class DemuxDocumentScraper(BaseScraper):
    '''Puts multiple Document Scrapers into one.'''
    def __init__(self, document_scrapers):
        self._document_scrapers = document_scrapers

    def scrape(self, request, response):
        '''Iterate the scrapers, returning the first of the results.'''
        for scraper in self._document_scrapers:
            scrape_info = scraper.scrape(request, response)

            if scrape_info is None:
                continue

            if scrape_info['inline_urls'] or scrape_info['linked_urls']:
                return scrape_info

    def scrape_info(self, request, response):
        '''Iterate the scrapers and return a dict of results.

        Returns:
            dict: A dict where the keys are the scrapers instances and the
            values are the results. That is, a mapping from
            :class:`BaseDocumentScraper` to :class:`dict`.
        '''
        info = {}
        for scraper in self._document_scrapers:
            scrape_info = scraper.scrape(request, response)
            info[scraper] = scrape_info

        return info
