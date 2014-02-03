# encoding=utf-8
'''Processor.'''
import abc
import contextlib
import functools
import gettext
import logging
import os
import urllib.parse

from wpull.conversation import Body
from wpull.database import Status
from wpull.errors import (ProtocolError, ServerError, ConnectionRefused,
    DNSNotFound)
from wpull.http import Request, Response, RedirectTracker
from wpull.robotstxt import RobotsTxtPool, RobotsTxtSessionMixin
from wpull.scraper import HTMLScraper
from wpull.stats import Statistics
from wpull.url import URLInfo
import wpull.util
from wpull.waiter import LinearWaiter


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseProcessor(object, metaclass=abc.ABCMeta):
    '''Base class for processors.

    Processors contain the logic for processing requests.
    '''
    @contextlib.contextmanager
    @abc.abstractmethod
    def session(self, url_item):
        '''Return a new Processor Session.

        The Processor Session handles the logic for processing a single
        URL item.

        Args:
            url_item (URLItem): An instance of :class:`.engine.URLItem`.

        Returns:
            BaseProcessorSession: An instance of :class:`BaseProcessorSession`.
        '''
        pass

    def close(self):
        '''Run any clean up actions.'''
        pass


class BaseProcessorSession(object, metaclass=abc.ABCMeta):
    '''A session for a Processor.'''
    @abc.abstractmethod
    def should_fetch(self):
        '''Return whether the item's URL should be fetched.

        If a processor decides it does not need to fetch the URL,
        it should call :func:`.engine.URLItem.skip`.

        Returns:
            bool
        '''
        pass

    @abc.abstractmethod
    def new_request(self):
        '''Return a Request instance needed to process the item.

        Returns:
            BaseRequest: An instance of :class:`.conversation.BaseRequest`.
        '''
        pass

    @abc.abstractmethod
    def response_factory(self):
        '''Return a callable object that should make a Response instance.

        Returns:
            callable: An instance that will return an instance of
            :class:`.conversation.BaseResponse` when called.
        '''
        pass

    @abc.abstractmethod
    def handle_response(self, response):
        '''Process the response.

        Args:
            response (BaseResponse): An instance of
                :class:`.conversation.BaseResponse`

        Returns:
            bool: If ``True``, the Processor session has successfully
            processed the item and the Engine should not retry the item.
            Otherwise, the Engine will attempt to make a request again for
            this Processor Session.
        '''
        pass

    @abc.abstractmethod
    def handle_error(self, error):
        '''Process the error.

        Args:
            error: An exception instance.

        Returns:
            bool: If ``True``, the Processor session has successfully
            processed the item and the Engine should not retry the item.
            Otherwise, the Engine will attempt to make a request again for
            this Processor Session.
        '''
        pass

    def wait_time(self):
        '''Return the delay between requests.

        Returns:
            float: A time in seconds.
        '''
        return 0


class WebProcessor(BaseProcessor):
    '''HTTP processor.

    Args:
        url_filters: URL filters.
        document_scrapers: Document scrapers.
        file_writer: File writer.
        waiter: Waiter.
        statistics: Statistics.
        request_factory: A callable object that returns a new
            :class:`.http.Request`.
        retry_connrefused: If True, don't consider a connection refused error
            to be a permanent error.
        retry_dns_error: If True, don't consider a DNS resolution error to be
            permanent error.
        max_redirects: The maximum number of sequential redirects to be done
            before considering it as a redirect loop.
        robots: If True, robots.txt handling is enabled.

    :seealso: :class:`WebProcessorSession`,
        :class:`WebProcessorWithRobotsTxtSession`
    '''
    DOCUMENT_STATUS_CODES = (200, 206)
    '''Default status codes considered successfully fetching a document.'''

    NO_DOCUMENT_STATUS_CODES = (401, 403, 404, 405, 410,)
    '''Default status codes considered a permanent error.'''

    def __init__(self, url_filters=None, document_scrapers=None,
    file_writer=None, waiter=None, statistics=None, request_factory=None,
    retry_connrefused=False, retry_dns_error=False, max_redirects=20,
    robots=False, post_data=None):
        self._url_filters = url_filters or ()
        self._document_scrapers = document_scrapers or ()
        self._file_writer = file_writer
        self._waiter = waiter or LinearWaiter()
        self._statistics = statistics or Statistics()
        self._request_factory = request_factory or Request.new
        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error
        self._max_redirects = max_redirects
        self._post_data = post_data

        if robots:
            self._robots_txt_pool = RobotsTxtPool()
            self._session_class = functools.partial(
                WebProcessorWithRobotsTxtSession,
                robots_txt_pool=self._robots_txt_pool
            )
        else:
            self._robots_txt_pool = None
            self._session_class = WebProcessorSession

        self._statistics.start()

    @contextlib.contextmanager
    def session(self, url_item):
        session = self._session_class(
            url_item=url_item,
            url_filters=self._url_filters,
            document_scrapers=self._document_scrapers,
            file_writer_session=self._file_writer.session(),
            waiter=self._waiter,
            statistics=self._statistics,
            request_factory=self._request_factory,
            retry_connrefused=self._retry_connrefused,
            retry_dns_error=self._retry_dns_error,
            max_redirects=self._max_redirects,
            post_data=self._post_data,
        )
        yield session

    def close(self):
        self._statistics.stop()


class WebProcessorSession(BaseProcessorSession):
    '''Fetches an HTTP document.

    This Processor Session will handle document redirects within the same
    Session. HTTP errors such as 404 are considered permanent errors.
    HTTP errors like 500 are considered transient errors and are handled in
    subsequence sessions by marking the item as "error".

    If a successful document has been downloaded, it will be scraped for
    URLs to be added to the URL table. This Processor Session is very simple;
    it cannot handle JavaScript or Flash plugins.
    '''
    def __init__(self, **kwargs):
        self._url_item = kwargs.pop('url_item')
        self._url_filters = kwargs.pop('url_filters')
        self._document_scrapers = kwargs.pop('document_scrapers')
        self._file_writer_session = kwargs.pop('file_writer_session')
        self._waiter = kwargs.pop('waiter')
        self._statistics = kwargs.pop('statistics')
        self._request_factory = kwargs.pop('request_factory')

        self._retry_connrefused = kwargs.pop('retry_connrefused')
        self._retry_dns_error = kwargs.pop('retry_dns_error')

        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None
        self._redirect_url_info = None
        self._post_data = kwargs.pop('post_data')
        # TODO: RedirectTracker should be depedency injected
        self._redirect_tracker = RedirectTracker(
            max_redirects=kwargs.pop('max_redirects')
        )

    @property
    def _next_url_info(self):
        '''Return the next URLInfo to be processed.

        This returns either the original URLInfo or the next URLinfo
        containing the redirect link.
        '''
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
            url_info.encoding,
            referer=url_record.referrer,
        )

        if url_record.post_data or self._post_data:
            if not self._redirect_tracker.is_redirect() \
            or self._redirect_tracker.is_repeat():
                self._add_post_data(self._request)

        if self._file_writer_session \
        and not self._redirect_url_info and self._request:
            self._request = self._file_writer_session.process_request(
                self._request)

        return self._request

    def _new_request_instance(self, url, encoding, referer=None):
        '''Return a new Request.

        This function adds the referrer URL.
        '''
        request = self._request_factory(url, url_encoding=encoding)

        if 'Referer' not in request.fields and referer:
            request.fields['Referer'] = referer

        return request

    def _add_post_data(self, request):
        if self._url_item.url_record.post_data:
            data = wpull.util.to_bytes(self._url_item.url_record.post_data)
        else:
            data = wpull.util.to_bytes(self._post_data)

        request.method = 'POST'
        request.fields['Content-Type'] = 'application/x-www-form-urlencoded'
        request.fields['Content-Length'] = str(len(data))

        _logger.debug('Posting with data {0}.'.format(data))

        with wpull.util.reset_file_offset(request.body.content_file):
            request.body.content_file.write(data)

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
        self._redirect_tracker.load(response)

        if self._redirect_tracker.is_redirect():
            return self._handle_redirect(response)
        elif response.status_code in self._document_codes:
            return self._handle_document(response)
        elif response.status_code in self._no_document_codes:
            return self._handle_no_document(response)
        else:
            return self._handle_document_error(response)

    def _handle_document(self, response):
        _logger.debug('Got a document.')

        if self._file_writer_session:
            self._file_writer_session.save_document(response)

        self._scrape_document(self._request, response)
        self._waiter.reset()
        self._statistics.increment(response.body.content_size)
        self._url_item.set_status(Status.done)

        return True

    @classmethod
    def _parse_url(cls, url, encoding):
        '''Parse and return a URLInfo.

        This function logs a warning if the URL cannot be parsed and returns
        None.
        '''
        try:
            url_info = URLInfo.parse(url, encoding=encoding)
        except ValueError as error:
            _logger.warning(_('Discarding malformed URL ‘{url}’: {error}.')\
                .format(url=url, error=error))
        else:
            return url_info

    def _handle_no_document(self, response):
        '''Callback for when no useful document is received.'''
        self._waiter.reset()

        if self._file_writer_session:
            self._file_writer_session.discard_document(response)

        self._url_item.set_status(Status.skipped)

        return True

    def _handle_document_error(self, response):
        '''Callback for when the document only describes an server error.'''
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
        '''Process a redirect.

        Returns:
            True if the redirect was finished. False if there is a redirect
            remaining.
        '''
        self._waiter.reset()

        if self._redirect_tracker.next_location() \
        and not self._redirect_tracker.exceeded():
            url = self._redirect_tracker.next_location()
            url = urllib.parse.urljoin(self._request.url_info.url, url)

            _logger.debug('Got redirect to {url}.'.format(url=url))

            self._redirect_url_info = URLInfo.parse(url)
        else:
            _logger.warning(_('Redirection failure.'))

            self._statistics.errors[ProtocolError] += 1
            self._url_item.set_status(Status.error)

            return True

    def wait_time(self):
        return self._waiter.get()

    def _filter_url(self, url_info, url_record):
        '''Filter the URL and return the filters that were used.

        Returns:
            a tuple containing a set of filters that passed and a set of
            filters that failed.
        '''
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
        '''Return if any URL filter has failed.'''
        failed = self._filter_url(url_info, url_record)[1]
        return len(failed) == 0

    def _scrape_document(self, request, response):
        '''Scrape the document for URLs.'''
        num_inline_urls = 0
        num_linked_urls = 0

        for scraper in self._document_scrapers:
            new_inline, new_linked = self._process_scraper(
                scraper, request, response
            )
            num_inline_urls += new_inline
            num_linked_urls += new_linked

        _logger.debug('Found URLs: inline={0} linked={1}'.format(
            num_inline_urls, num_linked_urls
        ))

    def _process_scraper(self, scraper, request, response):
        '''Run the scraper on the response.'''
        scrape_info = scraper.scrape(request, response)

        if not scrape_info:
            return 0, 0

        if isinstance(scraper, HTMLScraper):
            link_type = 'html'
        else:
            link_type = None

        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']
        encoding = scrape_info['encoding']

        assert encoding

        inline_url_infos = set()
        linked_url_infos = set()

        for url in inline_urls:
            url_info = self._parse_url(url, encoding)
            if url_info:
                inline_url_infos.add(url_info)

        for url in linked_urls:
            url_info = self._parse_url(url, encoding)
            if url_info:
                linked_url_infos.add(url_info)

        self._url_item.add_inline_url_infos(
            inline_url_infos, encoding=encoding)
        self._url_item.add_linked_url_infos(
            linked_url_infos, encoding=encoding, link_type=link_type)

        return len(inline_url_infos), len(linked_url_infos)


class WebProcessorWithRobotsTxtSession(
RobotsTxtSessionMixin, WebProcessorSession):
    '''Checks the robots.txt before fetching a URL.'''
    pass
