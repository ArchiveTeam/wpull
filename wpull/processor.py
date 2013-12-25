import abc
import contextlib
import logging
import urllib.parse

from wpull.database import Status
from wpull.errors import ProtocolError, ServerError
from wpull.http import Request
from wpull.stats import Statistics
import wpull.version
from wpull.waiter import LinearWaiter


_logger = logging.getLogger(__name__)


class BaseProcessor(object, metaclass=abc.ABCMeta):
    @contextlib.contextmanager
    @abc.abstractmethod
    def session(self):
        pass

    @abc.abstractproperty
    def statistics(self):
        pass


class BaseProcessorSession(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def new_request(self, url_record, url_info):
        pass

    @abc.abstractmethod
    def accept_response(self, response, error=None):
        pass

    @abc.abstractmethod
    def wait_time(self):
        pass

    @abc.abstractmethod
    def get_inline_urls(self):
        pass

    @abc.abstractmethod
    def get_linked_urls(self):
        pass


class WebProcessor(BaseProcessor):
    def __init__(self, url_filters=None, document_scrapers=None,
    file_writer=None, waiter=None, statistics=None):
        self._url_filters = url_filters or ()
        self._document_scrapers = document_scrapers or ()
        self._file_writer = file_writer
        self._waiter = waiter or LinearWaiter()
        self._statistics = statistics or Statistics()

    @contextlib.contextmanager
    def session(self):
        session = WebProcessorSession(
            self._url_filters,
            self._document_scrapers,
            self._file_writer,
            self._waiter,
            self._statistics,
        )
        yield session

    @property
    def statistics(self):
        return self._statistics


class WebProcessorSession(BaseProcessorSession):
    def __init__(self, url_filters, document_scrapers, file_writer, waiter,
    statistics):
        self._url_filters = url_filters
        self._document_scrapers = document_scrapers
        self._file_writer = file_writer
        self._request = None
        self._inline_urls = set()
        self._linked_urls = set()
        self._redirect_url = None
        self._waiter = waiter
        self._statistics = statistics

    def new_request(self, url_record, url_info):
        if not self._filter_test_url(url_info, url_record):
            _logger.debug('Rejecting {url} due to filters.'.format(
                url=url_info.url))
            return

        if self._redirect_url:
            self._request = self._new_request_instance(self._redirect_url)
            self._redirect_url = None
        else:
            self._request = self._new_request_instance(url_info.url)

            if self._file_writer:
                self._file_writer.rewrite_request(self._request)

        return self._request

    def _new_request_instance(self, url):
        request = Request.new(url)
        request.fields['User-Agent'] = 'Mozilla/5.0 (compatible) Wpull/{0}'\
            .format(wpull.version.__version__)

        return request

    def accept_response(self, response, error=None):
        if error:
            return self._accept_error(error)

        if response.status_code in (301, 302, 303, 307, 308):
            # TODO: handle max redirects
            if 'location' in response.fields:
                url = response.fields['location']
                url = urllib.parse.urljoin(self._request.url_info.url, url)
                _logger.debug('Got redirect to {url}.'.format(url=url))
                self._redirect_url = url
                self._waiter.reset()
                return
            else:
                self._statistics.errors[ProtocolError] += 1
                return Status.error

        if response.status_code == 200:
            _logger.debug('Got a document.')
            self._scrape_document(self._request, response)
            if self._file_writer:
                self._file_writer.write_response(self._request, response)
            self._waiter.reset()
            self._statistics.files += 1
            self._statistics.size += response.body.http_size
            return Status.done

        if response.status_code == 404:
            self._waiter.reset()
            return Status.skipped

        self._waiter.increment()

        self._statistics.errors[ServerError] += 1

        return Status.error

    def _accept_error(self, error):
        self._statistics.errors[type(error)] += 1
        self._waiter.increment()

    def wait_time(self):
        return self._waiter.get()

    def get_inline_urls(self):
        return self._inline_urls

    def get_linked_urls(self):
        return self._linked_urls

    def _filter_test_url(self, url_info, url_record):
        results = []
        for url_filter in self._url_filters:
            result = url_filter.test(url_info, url_record)
            _logger.debug(
                'URL Filter test {0} returned {1}'.format(url_filter, result))
            results.append(result)

        return all(results)

    def _scrape_document(self, request, response):
        for scraper in self._document_scrapers:
            new_inline_urls, new_linked_urls = scraper.scrape(
                request, response)
            self._inline_urls.update(new_inline_urls)
            self._linked_urls.update(new_linked_urls)

        _logger.debug('Found URLs: inline={0} linked={1}'.format(
            len(self._inline_urls), len(self._linked_urls)
        ))
