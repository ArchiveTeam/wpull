# encoding=utf-8
import abc
import contextlib
import gettext
import logging
import urllib.parse

from wpull.database import Status
from wpull.errors import (ProtocolError, ServerError, ConnectionRefused,
    DNSNotFound)
from wpull.http import Request, Response
from wpull.robotstxt import (RobotsTxtPool, RobotsTxtSubsession,
    RobotsTxtNotLoaded)
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
        else:
            self._robots_txt_pool = None

        self._statistics.start()

    @contextlib.contextmanager
    def session(self, url_item):
        session = WebProcessorSession(
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
            self._robots_txt_pool,
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
    retry_connrefused, retry_dns_error, max_redirects, robots_txt_pool):
        self._url_item = url_item
        self._url_filters = url_filters
        self._document_scrapers = document_scrapers
        self._file_writer_session = file_writer_session
        self._request = None
        self._inline_urls = set()
        self._linked_urls = set()
        self._redirect_url = None
        self._waiter = waiter
        self._statistics = statistics
        self._request_factory = request_factory
        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error
        self._redirects_remaining = max_redirects
        self._state = self.State.normal
        self._redirect_codes = WebProcessor.REDIRECT_STATUS_CODES
        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        if robots_txt_pool:
            self._robots_txt_subsession = RobotsTxtSubsession(robots_txt_pool,
                self._new_request_instance)
        else:
            self._robots_txt_subsession = None

    def new_request(self):
        url_info = self._url_item.url_info
        url_record = self._url_item.url_record

        if not self._filter_test_url(url_info, url_record):
            _logger.debug('Rejecting {url} due to filters.'.format(
                url=url_info.url))
            self._url_item.skip()
            return

        self._request = self._new_request_instance(
            url_info.url,
            url_record.referrer,
        )

        if self._redirect_url:
            self._request = self._new_request_instance(
                self._redirect_url,
                url_record.referrer,
            )

        if self._robots_txt_subsession:
            self._check_robots_and_rewrite()

        if self._file_writer_session \
        and self._state == self.State.normal \
        and not self._redirect_url and self._request:
            self._request = self._file_writer_session.process_request(
                self._request)

        return self._request

    def _new_request_instance(self, url, referer=None):
        request = self._request_factory(url)

        if 'Referer' not in request.fields and referer:
            request.fields['Referer'] = referer

        return request

    def _check_robots_and_rewrite(self):
        if self._state == self.State.normal:
            try:
                ok = self._robots_txt_subsession.can_fetch(self._request)
            except RobotsTxtNotLoaded:
                self._state = self.State.robotstxt
                self._request = self._robots_txt_subsession.rewrite_request(
                    self._request)
            else:
                if not ok:
                    _logger.debug('Rejecting {url} due to robots.txt'.format(
                        url=self._request.url_info.url))
                    self._request = None
        else:
            self._request = self._robots_txt_subsession.rewrite_request(
                self._request)

    def response_factory(self):
        def factory(*args, **kwargs):
            response = Response(*args, **kwargs)

            if self._file_writer_session:
                self._file_writer_session.process_response(response)

            return response

        return factory

    def handle_response(self, response):
        if self._state == self.State.robotstxt:
            self._handle_robots_txt_response(response)
            return

        self._redirect_url = None

        self._url_item.set_value(status_code=response.status_code)

        if response.status_code in self._redirect_codes:
            return self._handle_redirect(response)
        elif response.status_code in self._document_codes:
            return self._handle_document(response)
        elif response.status_code in self._no_document_codes:
            return self._handle_no_document(response)
        else:
            return self._handle_document_error(response)

    def _handle_robots_txt_response(self, response):
        result = self._robots_txt_subsession.check_response(response)

        if result == RobotsTxtSubsession.Result.done \
        or result == RobotsTxtSubsession.Result.fail:
            self._state = self.State.normal
            self._waiter.reset()
        elif result == RobotsTxtSubsession.Result.redirect:
            self._waiter.reset()
        elif result == RobotsTxtSubsession.Result.retry:
            self._waiter.increment()
        else:
            raise NotImplementedError()

    def _handle_document(self, response):
        _logger.debug('Got a document.')

        self._scrape_document(self._request, response)
        self._url_item.add_inline_url_infos(
            [URLInfo.parse(url) for url in self._inline_urls])
        self._url_item.add_linked_url_infos(
            [URLInfo.parse(url) for url in self._linked_urls])

        if self._file_writer_session:
            self._file_writer_session.save_document(response)

        self._waiter.reset()
        self._statistics.increment(response.body.content_size)
        self._url_item.set_status(Status.done)

        return True

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
            self._redirect_url = url
            self._redirects_remaining -= 1
        else:
            _logger.warning(_('Redirection failure.'))
            self._statistics.errors[ProtocolError] += 1
            self._url_item.set_status(Status.error)
            return True

    def wait_time(self):
        return self._waiter.get()

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
                request, response) or ((), ())
            self._inline_urls.update(new_inline_urls)
            self._linked_urls.update(new_linked_urls)

        _logger.debug('Found URLs: inline={0} linked={1}'.format(
            len(self._inline_urls), len(self._linked_urls)
        ))
