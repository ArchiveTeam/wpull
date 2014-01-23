# encoding=utf-8
import abc
import contextlib
import gettext
import logging
import os
import urllib.parse

from wpull.database import Status
from wpull.errors import (ProtocolError, ServerError, ConnectionRefused,
    DNSNotFound)
from wpull.http import Request, Response, Body
from wpull.robotstxt import RobotsTxtPool, RobotsTxtSessionMixin
from wpull.stats import Statistics
from wpull.url import URLInfo
from wpull.waiter import LinearWaiter


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseProcessor(object, metaclass=abc.ABCMeta):
    @contextlib.contextmanager
    @abc.abstractmethod
    def session(self, url_item):
        pass

    @abc.abstractproperty
    def statistics(self):
        pass

    def close(self):
        pass


class BaseProcessorSession(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def should_fetch(self):
        pass

    @abc.abstractmethod
    def new_request(self):
        pass

    @abc.abstractmethod
    def response_factory(self):
        pass

    @abc.abstractmethod
    def handle_response(self, response):
        pass

    @abc.abstractmethod
    def handle_error(self, error):
        pass

    def wait_time(self):
        return 0


class WebProcessor(BaseProcessor):
    REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
    DOCUMENT_STATUS_CODES = (200, 206)
    NO_DOCUMENT_STATUS_CODES = (401, 403, 404, 405, 410,)

    def __init__(self, url_filters=None, document_scrapers=None,
    file_writer=None, waiter=None, statistics=None, request_factory=None,
    retry_connrefused=False, retry_dns_error=False, max_redirects=20,
    robots=False):
        self._url_filters = url_filters or ()
        self._document_scrapers = document_scrapers or ()
        self._file_writer = file_writer
        self._waiter = waiter or LinearWaiter()
        self._statistics = statistics or Statistics()
        self._request_factory = request_factory or Request.new
        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error
        self._max_redirects = max_redirects

        if robots:
            self._robots_txt_pool = RobotsTxtPool()
            self._session_class = WebProcessorWithRobotsTxtSession
        else:
            self._robots_txt_pool = None
            self._session_class = WebProcessorSession

        self._statistics.start()

    @contextlib.contextmanager
    def session(self, url_item):
        session = self._session_class(
            url_item,
            self._url_filters,
            self._document_scrapers,
            self._file_writer.session(),
            self._waiter,
            self._statistics,
            self._request_factory,
            self._retry_connrefused,
            self._retry_dns_error,
            self._max_redirects,
        )
        yield session

    @property
    def statistics(self):
        return self._statistics

    def close(self):
        self._statistics.stop()


class WebProcessorSession(BaseProcessorSession):
    class State(object):
        normal = 1
        robotstxt = 2

    def __init__(self, url_item, url_filters, document_scrapers,
    file_writer_session, waiter, statistics, request_factory,
    retry_connrefused, retry_dns_error, max_redirects):
        self._url_item = url_item
        self._url_filters = url_filters
        self._document_scrapers = document_scrapers
        self._file_writer_session = file_writer_session
        self._waiter = waiter
        self._statistics = statistics
        self._request_factory = request_factory

        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error

        self._redirect_codes = WebProcessor.REDIRECT_STATUS_CODES
        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None
        self._redirect_url_info = None
        self._redirects_remaining = max_redirects

    @property
    def _next_url_info(self):
        return self._redirect_url_info or self._url_item.url_info

    def should_fetch(self):
        url_info = self._next_url_info
        url_record = self._url_item.url_record

        if self._is_url_filtered(url_info, url_record):
            return True

        else:
            _logger.debug('Rejecting {url} due to filters.'.format(
                url=url_info.url))
            self._url_item.skip()

            return False

    def new_request(self):
        url_info = self._next_url_info
        url_record = self._url_item.url_record

        self._request = self._new_request_instance(
            url_info.url,
            url_record.referrer,
        )

        if self._file_writer_session \
        and not self._redirect_url_info and self._request:
            self._request = self._file_writer_session.process_request(
                self._request)

        return self._request

    def _new_request_instance(self, url, referer=None):
        request = self._request_factory(url)

        if 'Referer' not in request.fields and referer:
            request.fields['Referer'] = referer

        return request

    def response_factory(self):
        def factory(*args, **kwargs):
            # TODO: Response should be dependency injected
            response = Response(*args, **kwargs)
            # FIXME: we should be using --directory-prefix instead of CWD.
            response.body.content_file = Body.new_temp_file(os.getcwd())

            if self._file_writer_session:
                self._file_writer_session.process_response(response)

            return response

        return factory

    def handle_response(self, response):
        self._redirect_url_info = None

        self._url_item.set_value(status_code=response.status_code)

        if response.status_code in self._redirect_codes:
            return self._handle_redirect(response)
        elif response.status_code in self._document_codes:
            return self._handle_document(response)
        elif response.status_code in self._no_document_codes:
            return self._handle_no_document(response)
        else:
            return self._handle_document_error(response)

    def _handle_document(self, response):
        _logger.debug('Got a document.')

        inline_urls, linked_urls = self._scrape_document(
            self._request, response)

        inline_url_infos = set()
        linked_url_infos = set()

        for url in inline_urls:
            url_info = self._parse_url(url)
            if url_info:
                inline_url_infos.add(url_info)

        for url in linked_urls:
            url_info = self._parse_url(url)
            if url_info:
                linked_url_infos.add(url_info)

        self._url_item.add_inline_url_infos(inline_url_infos)
        self._url_item.add_linked_url_infos(linked_url_infos)

        if self._file_writer_session:
            self._file_writer_session.save_document(response)

        self._waiter.reset()
        self._statistics.increment(response.body.content_size)
        self._url_item.set_status(Status.done)

        return True

    @classmethod
    def _parse_url(cls, url):
        try:
            url_info = URLInfo.parse(url)
        except ValueError as error:
            _logger.warning(_('Discarding malformed URL ‘{url}’: {error}.')\
                .format(url=url, error=error))
        else:
            return url_info

    def _handle_no_document(self, response):
        self._waiter.reset()

        if self._file_writer_session:
            self._file_writer_session.discard_document(response)

        self._url_item.set_status(Status.skipped)

        return True

    def _handle_document_error(self, response):
        self._waiter.increment()

        if self._file_writer_session:
            self._file_writer_session.discard_document(response)

        self._statistics.errors[ServerError] += 1
        self._url_item.set_status(Status.error)

        return True

    def handle_error(self, error):
        self._statistics.errors[type(error)] += 1
        self._waiter.increment()

        if isinstance(error, ConnectionRefused) \
        and not self._retry_connrefused:
            self._url_item.set_status(Status.skipped)
        elif isinstance(error, DNSNotFound) and not self._retry_dns_error:
            self._url_item.set_status(Status.skipped)
        else:
            self._url_item.set_status(Status.error)

        return True

    def _handle_redirect(self, response):
        self._waiter.reset()

        if 'location' in response.fields and self._redirects_remaining > 0:
            url = response.fields['location']
            url = urllib.parse.urljoin(self._request.url_info.url, url)

            _logger.debug('Got redirect to {url}.'.format(url=url))

            self._redirect_url_info = URLInfo.parse(url)
            self._redirects_remaining -= 1
        else:
            _logger.warning(_('Redirection failure.'))

            self._statistics.errors[ProtocolError] += 1
            self._url_item.set_status(Status.error)

            return True

    def wait_time(self):
        return self._waiter.get()

    def _filter_url(self, url_info, url_record):
        passed = set()
        failed = set()

        for url_filter in self._url_filters:
            result = url_filter.test(url_info, url_record)

            _logger.debug(
                'URL Filter test {0} returned {1}'.format(url_filter, result))

            if result:
                passed.add(url_filter)
            else:
                failed.add(url_filter)

        return passed, failed

    def _is_url_filtered(self, url_info, url_record):
        failed = self._filter_url(url_info, url_record)[1]
        return len(failed) == 0

    def _scrape_document(self, request, response):
        inline_urls = set()
        linked_urls = set()

        for scraper in self._document_scrapers:
            new_inline_urls, new_linked_urls = scraper.scrape(
                request, response) or ((), ())
            inline_urls.update(new_inline_urls)
            linked_urls.update(new_linked_urls)

        _logger.debug('Found URLs: inline={0} linked={1}'.format(
            len(inline_urls), len(linked_urls)
        ))

        return inline_urls, linked_urls


class WebProcessorWithRobotsTxtSession(
RobotsTxtSessionMixin, WebProcessorSession):
    pass
