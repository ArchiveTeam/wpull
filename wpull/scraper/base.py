'''Base classes'''
import abc
import collections

from wpull.document.base import BaseDocumentReader


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


class BaseDocumentScraper(BaseDocumentReader):
    '''Base class for clases that scrape documents.'''
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
        pass


class DemuxDocumentScraper(object):
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
