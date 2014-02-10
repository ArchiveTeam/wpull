# encoding=utf-8
'''Processor.'''
import abc
import gettext
import logging
import os
import tornado.gen

from wpull.conversation import Body
from wpull.database import Status
from wpull.errors import (ProtocolError, ServerError, ConnectionRefused,
    DNSNotFound, NetworkError)
from wpull.http import Response, Request
from wpull.scraper import HTMLScraper, DemuxDocumentScraper
from wpull.stats import Statistics
from wpull.url import URLInfo, DemuxURLFilter
import wpull.util
from wpull.waiter import LinearWaiter
from wpull.writer import NullWriter
from wpull.web import RichClientResponseType


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseProcessor(object, metaclass=abc.ABCMeta):
    '''Base class for processors.

    Processors contain the logic for processing requests.
    '''
    @tornado.gen.coroutine
    def process(self, url_item):
        '''Process an URL Item.

        Args:
            url_item (URLItem): An instance of :class:`.engine.URLItem`.

        This function handles the logic for processing a single
        URL item.

        It must call one of :func:`.engine.URLItem.set_status` or
        :func:`.engine.URLItem.skip`.
        '''
        pass

    def close(self):
        '''Run any clean up actions.'''
        pass


class WebProcessor(BaseProcessor):
    '''HTTP processor.

    Args:
        rich_client (RichClient): An instance of :class:`.http.RichClient`.
        url_filter (DemuxURLFilter): An instance of
            :class:`.url.DemuxURLFilter`.
        document_scraper (DemuxDocumentScraper): An instance of
            :class:`.scaper.DemuxDocumentScraper`.
        file_writer: File writer.
        waiter: Waiter.
        statistics: Statistics.
        request_factory: A callable object that returns a new
            :class:`.http.Request` via :func:`.http.Request.new`.
        retry_connrefused: If True, don't consider a connection refused error
            to be a permanent error.
        retry_dns_error: If True, don't consider a DNS resolution error to be
            permanent error.
        post_data (str): If provided, all requests will be POSTed with the
            given `post_data`. `post_data` must be in percent-encoded
            query format ("application/x-www-form-urlencoded").

    :seealso: :class:`WebProcessorSession`,
        :class:`WebProcessorWithRobotsTxtSession`
    '''
    DOCUMENT_STATUS_CODES = (200, 206)
    '''Default status codes considered successfully fetching a document.'''

    NO_DOCUMENT_STATUS_CODES = (401, 403, 404, 405, 410,)
    '''Default status codes considered a permanent error.'''

    def __init__(self, rich_client,
    url_filter=None, document_scraper=None, file_writer=None,
    waiter=None, statistics=None, request_factory=Request.new,
    retry_connrefused=False, retry_dns_error=False, post_data=None):
        self._rich_client = rich_client
        self._url_filter = url_filter or DemuxURLFilter([])
        self._document_scraper = document_scraper or DemuxDocumentScraper([])
        self._file_writer = file_writer or NullWriter()
        self._waiter = waiter or LinearWaiter()
        self._statistics = statistics or Statistics()
        self._request_factory = request_factory
        self._retry_connrefused = retry_connrefused
        self._retry_dns_error = retry_dns_error
        self._post_data = post_data
        self._session_class = WebProcessorSession

    @property
    def rich_client(self):
        return self._rich_client

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
    def retry_dns_error(self):
        return self._retry_dns_error

    @property
    def retry_connrefused(self):
        return self._retry_connrefused

    @property
    def post_data(self):
        return self._post_data

    @tornado.gen.coroutine
    def process(self, url_item):
        session = self._session_class(self, url_item)
        raise tornado.gen.Return((yield session.process()))

    def close(self):
        self._rich_client.close()


class WebProcessorSession(object):
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
        super().__init__()
        self._processor = processor
        self._url_item = url_item
        self._file_writer_session = processor.file_writer.session()
        self._rich_client_session = processor.rich_client.session(
            self._new_initial_request()
        )

        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None

    def _new_initial_request(self):
        '''Return a new Request to be passed to the Rich Client.'''
        url_info = self._url_item.url_info
        url_record = self._url_item.url_record

        request = self._processor.request_factory(
            url_info.url, url_encoding=url_info.encoding)

        self._populate_common_request(request)

        if url_record.post_data or self._processor.post_data:
            self._add_post_data(request)

        if self._file_writer_session:
            request = self._file_writer_session.process_request(request)

        return request

    def _populate_common_request(self, request):
        '''Populate the Request with common fields.

        This function adds the referrer URL.
        '''
        url_record = self._url_item.url_record

        if url_record.referrer:
            request.fields['Referer'] = url_record.referrer

    @tornado.gen.coroutine
    def process(self):
        while not self._rich_client_session.done:
            if not self._should_fetch():
                self._url_item.skip()
                break

            is_done = yield self._process_one()

            wait_time = self._processor.waiter.get()

            if wait_time:
                _logger.debug('Sleeping {0}.'.format(wait_time))
                yield wpull.util.sleep(wait_time)

            if is_done:
                break

        if self._request:
            self._close_instance_body(self._request)

    @tornado.gen.coroutine
    def _process_one(self):
        self._request = request = self._rich_client_session.next_request

        _logger.info(_('Fetching ‘{url}’.').format(url=request.url_info.url))

        try:
            response = yield self._rich_client_session.fetch(
                response_factory=self._new_response_factory()
            )
        except (NetworkError, ProtocolError) as error:
            _logger.error(
                _('Fetching ‘{url}’ encountered an error: {error}')\
                    .format(url=request.url_info.url, error=error)
            )

            response = None
            is_done = self._handle_error(error)
        else:
            _logger.info(
                _('Fetched ‘{url}’: {status_code} {reason}. '
                    'Length: {content_length} [{content_type}].').format(
                    url=request.url_info.url,
                    status_code=response.status_code,
                    reason=response.status_reason,
                    content_length=response.fields.get('Content-Length'),
                    content_type=response.fields.get('Content-Type'),
                )
            )

            if self._rich_client_session.response_type \
            != RichClientResponseType.robots:
                is_done = self._handle_response(response)
            else:
                _logger.debug('Not handling response {0}.'.format(
                    self._rich_client_session.response_type))
                is_done = False

            self._close_instance_body(response)

        raise tornado.gen.Return(is_done)

    @property
    def _next_url_info(self):
        '''Return the next URLInfo to be processed.

        This returns either the original URLInfo or the next URLinfo
        containing the redirect link.
        '''
        return self._rich_client_session.next_request.url_info

    def _should_fetch(self):
        '''Return whether the URL should be fetched.'''
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

            return False

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

    def _new_response_factory(self):
        '''Return a new Response factory.'''
        def factory(*args, **kwargs):
            # TODO: Response should be dependency injected
            response = Response(*args, **kwargs)
            # FIXME: we should be using --directory-prefix instead of CWD.
            response.body.content_file = Body.new_temp_file(os.getcwd())

            if self._file_writer_session:
                self._file_writer_session.process_response(response)

            return response

        return factory

    def _handle_response(self, response):
        '''Process the response.'''
        self._url_item.set_value(status_code=response.status_code)

        if self._rich_client_session.redirect_tracker.is_redirect():
            return self._handle_redirect(response)
        elif response.status_code in self._document_codes:
            return self._handle_document(response)
        elif response.status_code in self._no_document_codes:
            return self._handle_no_document(response)
        else:
            return self._handle_document_error(response)

    def _handle_document(self, response):
        '''Process a document response.'''
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

    def _handle_error(self, error):
        '''Process an error.'''
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
        '''Process a redirect.'''
        self._processor.waiter.reset()
        return False

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

    def _close_instance_body(self, instance):
        '''Close any files on instance.

        This function will attempt to call ``body.content_file.close`` on
        the instance.
        '''
        if hasattr(instance, 'body') \
        and hasattr(instance.body, 'content_file') \
        and instance.body.content_file:
            instance.body.content_file.close()
