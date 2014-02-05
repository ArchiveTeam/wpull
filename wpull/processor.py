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
from wpull.scraper import HTMLScraper, DemuxDocumentScraper
from wpull.stats import Statistics
from wpull.url import URLInfo, DemuxURLFilter
import wpull.util
from wpull.waiter import LinearWaiter
from wpull.writer import NullWriter


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
        url_filter (DemuxURLFilter): An instance of
            :class:`.url.DemuxURLFilter`.
        document_scraper (DemuxDocumentScraper): An instance of
            :class:`.scaper.DemuxDocumentScraper`.
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

    def __init__(self, url_filter=None, document_scraper=None,
    file_writer=None, waiter=None, statistics=None, request_factory=None,
    retry_connrefused=False, retry_dns_error=False, max_redirects=20,
    robots=False, post_data=None):
        self._url_filter = url_filter or DemuxURLFilter([])
        self._document_scraper = document_scraper or DemuxDocumentScraper([])
        self._file_writer = file_writer or NullWriter()
        self._waiter = waiter or LinearWaiter()
        self._statistics = statistics or Statistics()
        self._request_factory = request_factory or Request.new
        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error
        self._max_redirects = max_redirects
        self._post_data = post_data

        if robots:
            # TODO: RobotsTxtPool should be dependency injected
            self._robots_txt_pool = RobotsTxtPool()
            self._session_class = functools.partial(
                WebProcessorWithRobotsTxtSession,
                robots_txt_pool=self._robots_txt_pool
            )
        else:
            self._robots_txt_pool = None
            self._session_class = WebProcessorSession

        self._statistics.start()

    @property
    def url_filter(self):
        return self._url_filter

    @property
    def document_scraper(self):
        return self._document_scraper

    @property
    def file_writer(self):
        return self._file_writer

    @property
    def waiter(self):
        return self._waiter

    @property
    def statistics(self):
        return self._statistics

    @property
    def request_factory(self):
        return self._request_factory

    @property
    def retry_connrefused(self):
        return self._retry_connrefused

    @property
    def max_redirects(self):
        return self._max_redirects

    @property
    def post_data(self):
        return self._post_data

    @contextlib.contextmanager
    def session(self, url_item):
        session = self._session_class(
            self,
            url_item,
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
    def __init__(self, processor, url_item):
        self._processor = processor
        self._url_item = url_item
        self._file_writer_session = processor.file_writer.session()

        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None
        self._redirect_url_info = None
        # TODO: RedirectTracker should be depedency injected
        self._redirect_tracker = RedirectTracker(
            max_redirects=processor.max_redirects
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
        test_info = self._processor.url_filter.test_info(url_info, url_record)

        if test_info['verdict']:
            return True

        else:
            _logger.debug(
                'Rejecting {url} due to filters: '
                'Passed={passed}. Failed={failed}.'.format(
                    url=url_info.url,
                    passed=test_info['passed'],
                    failed=test_info['failed']
            ))
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

        if url_record.post_data or self._processor.post_data:
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
        request = self._processor.request_factory(url, url_encoding=encoding)

        if 'Referer' not in request.fields and referer:
            request.fields['Referer'] = referer

        return request

    def _add_post_data(self, request):
        if self._url_item.url_record.post_data:
            data = wpull.util.to_bytes(self._url_item.url_record.post_data)
        else:
            data = wpull.util.to_bytes(self._processor.post_data)

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

        self._file_writer_session.save_document(response)
        self._scrape_document(self._request, response)
        self._processor.waiter.reset()
        self._processor.statistics.increment(response.body.content_size)
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
        self._processor.waiter.reset()
        self._file_writer_session.discard_document(response)
        self._url_item.set_status(Status.skipped)

        return True

    def _handle_document_error(self, response):
        '''Callback for when the document only describes an server error.'''
        self._processor.waiter.increment()
        self._file_writer_session.discard_document(response)
        self._processor.statistics.errors[ServerError] += 1
        self._url_item.set_status(Status.error)

        return True

    def handle_error(self, error):
        self._processor.statistics.errors[type(error)] += 1
        self._processor.waiter.increment()

        if isinstance(error, ConnectionRefused) \
        and not self._processor.retry_connrefused:
            self._url_item.set_status(Status.skipped)
        elif isinstance(error, DNSNotFound) \
        and not self._processor.retry_dns_error:
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
        self._processor.waiter.reset()

        if self._redirect_tracker.next_location() \
        and not self._redirect_tracker.exceeded():
            url = self._redirect_tracker.next_location()
            url = urllib.parse.urljoin(self._request.url_info.url, url)

            _logger.debug('Got redirect to {url}.'.format(url=url))

            self._redirect_url_info = URLInfo.parse(url)
        else:
            _logger.warning(_('Redirection failure.'))

            self._processor.statistics.errors[ProtocolError] += 1
            self._url_item.set_status(Status.error)

            return True

    def wait_time(self):
        return self._processor.waiter.get()

    def _scrape_document(self, request, response):
        '''Scrape the document for URLs.'''
        demux_info = self._processor.document_scraper.scrape_info(
            request, response)
        num_inline_urls = 0
        num_linked_urls = 0

        for scraper, scrape_info in demux_info.items():
            new_inline, new_linked = self._process_scrape_info(
                scraper, scrape_info
            )
            num_inline_urls += new_inline
            num_linked_urls += new_linked

        _logger.debug('Found URLs: inline={0} linked={1}'.format(
            num_inline_urls, num_linked_urls
        ))

    def _process_scrape_info(self, scraper, scrape_info):
        '''Collect the URLs from the scrape info dict.'''
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
