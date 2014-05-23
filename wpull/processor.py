# encoding=utf-8
'''Processor.'''
import abc
import copy
import gettext
import io
import json
import logging
import os
import tempfile
import time

import namedlist
import tornado.gen

import wpull.async
from wpull.conversation import Body
from wpull.database import Status
from wpull.document import HTMLReader
from wpull.errors import (ProtocolError, ServerError, ConnectionRefused,
    DNSNotFound, NetworkError)
from wpull.http.request import Response
from wpull.http.web import RichClientResponseType
from wpull.item import LinkType
from wpull.namevalue import NameValueRecord
from wpull.scraper import HTMLScraper, DemuxDocumentScraper, CSSScraper
from wpull.stats import Statistics
import wpull.string
from wpull.url import URLInfo
from wpull.urlfilter import DemuxURLFilter, SpanHostsFilter
import wpull.util
from wpull.waiter import LinearWaiter
from wpull.warc import WARCRecord
from wpull.writer import NullWriter


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
            url_item (:class:`.item.URLItem`): The URL item.

        This function handles the logic for processing a single
        URL item.

        It must call one of :meth:`.engine.URLItem.set_status` or
        :meth:`.engine.URLItem.skip`.
        '''
        pass

    def close(self):
        '''Run any clean up actions.'''
        pass


WebProcessorFetchParams = namedlist.namedtuple(
    'WebProcessorFetchParamsType',
    [
        ('retry_connrefused', False),
        ('retry_dns_error', False),
        ('post_data', None),
        ('strong_redirects', True),
        ('content_on_error', False),
    ]
)
'''WebProcessorFetchParams

Args:
    retry_connrefused: If True, don't consider a connection refused error
        to be a permanent error.
    retry_dns_error: If True, don't consider a DNS resolution error to be
        permanent error.
    post_data (str): If provided, all requests will be POSTed with the
        given `post_data`. `post_data` must be in percent-encoded
        query format ("application/x-www-form-urlencoded").
    strong_redirects (bool): If True, redirects are allowed to span hosts.
'''

WebProcessorInstances = namedlist.namedtuple(
    'WebProcessorInstancesType',
    [
        ('url_filter', DemuxURLFilter([])),
        ('document_scraper', DemuxDocumentScraper([])),
        ('file_writer', NullWriter()),
        ('waiter', LinearWaiter()),
        ('statistics', Statistics()),
        ('converter', None),
        ('phantomjs_controller', None),
    ]
)
'''WebProcessorInstances

Args:
    url_filter ( :class:`.urlfilter.DemuxURLFilter`): The URL filter.
    document_scraper (:class:`.scaper.DemuxDocumentScraper`): The document
        scraper.
    file_writer (:class`.writer.BaseWriter`): The file writer.
    waiter (:class:`.waiter.Waiter`): The Waiter.
    statistics (:class:`.stats.Statistics`): The Statistics.
    converter (:class:`.converter.BatchDocumentConverter`): The document
        converter.
    phantomjs_controller (:class:`PhantomJSController`): The PhantomJS
        controller.
'''


class WebProcessor(BaseProcessor):
    '''HTTP processor.

    Args:
        rich_client (:class:`.http.web.RichClient`): The rich web client.
        root_path (str): The root directory path.
        fetch_params: An instance of :class:`WebProcessorFetchParams`.
        instances: An instance of :class:`WebProcessorInstances`.

    .. seealso:: :class:`WebProcessorSession`,
        :class:`WebProcessorWithRobotsTxtSession`
    '''
    DOCUMENT_STATUS_CODES = (200, 206, 304,)
    '''Default status codes considered successfully fetching a document.'''

    NO_DOCUMENT_STATUS_CODES = (401, 403, 404, 405, 410,)
    '''Default status codes considered a permanent error.'''

    def __init__(self, rich_client, root_path, fetch_params, instances):
        self._rich_client = rich_client
        self._root_path = root_path
        self._fetch_params = fetch_params
        self._instances = instances
        self._session_class = WebProcessorSession

    @property
    def rich_client(self):
        '''The rich client.'''
        return self._rich_client

    @property
    def root_path(self):
        '''The root path.'''
        return self._root_path

    @property
    def instances(self):
        '''The processor instances.'''
        return self._instances

    @property
    def fetch_params(self):
        '''The fetch parameters.'''
        return self._fetch_params

    @tornado.gen.coroutine
    def process(self, url_item):
        session = self._session_class(self, url_item)
        raise tornado.gen.Return((yield session.process()))

    def close(self):
        '''Close the client and invoke document converter.'''
        self._rich_client.close()

        if self._instances.converter:
            self._instances.converter.convert_all()


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
        self._file_writer_session = processor.instances.file_writer.session()
        self._rich_client_session = None

        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None

    def _new_initial_request(self):
        '''Return a new Request to be passed to the Rich Client.'''
        url_info = self._url_item.url_info
        url_record = self._url_item.url_record

        request = self._processor.rich_client.request_factory(
            url_info.url, url_encoding=url_info.encoding)

        self._populate_common_request(request)

        if url_record.post_data or self._processor.fetch_params.post_data:
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
        verdict = self._should_fetch_reason(
            self._next_url_info, self._url_item.url_record)[0]

        if not verdict:
            self._url_item.skip()
            return

        self._rich_client_session = self._processor.rich_client.session(
            self._new_initial_request()
        )

        while not self._rich_client_session.done:
            verdict = self._should_fetch_reason(
                self._next_url_info, self._url_item.url_record)[0]

            if not verdict:
                self._url_item.skip()
                break

            is_done = yield self._process_one()

            wait_time = self._get_wait_time()

            if wait_time:
                _logger.debug('Sleeping {0}.'.format(wait_time))
                yield wpull.async.sleep(wait_time)

            if is_done:
                break

        if self._request:
            self._close_instance_body(self._request)

        if not self._url_item.is_processed:
            _logger.debug('Was not processed. Skipping.')
            self._url_item.skip()

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

                yield self._process_phantomjs(request, response)
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
        if not self._rich_client_session:
            return self._url_item.url_info

        return self._rich_client_session.next_request.url_info

    def _should_fetch_reason(self, url_info, url_record):
        '''Return info about whether the URL should be fetched.

        Returns:
            tuple: A two item tuple:

            1. bool: If True, the URL should be fetched.
            2. str: A short reason string explaining the verdict.
        '''
        test_info = self._processor.instances.url_filter.test_info(
            url_info, url_record
        )

        if test_info['verdict']:
            return True, 'filters'

        elif self._processor.fetch_params.strong_redirects \
        and self._rich_client_session \
        and self._rich_client_session.redirect_tracker \
        and self._rich_client_session.redirect_tracker.is_redirect \
        and len(test_info['failed']) == 1 \
        and 'SpanHostsFilter' in test_info['map'] \
        and not test_info['map']['SpanHostsFilter']:
            return True, 'redirect'

        else:
#             _logger.debug(
#                 'Rejecting {url} due to filters: '
#                 'Passed={passed}. Failed={failed}.'.format(
#                     url=url_info.url,
#                     passed=test_info['passed'],
#                     failed=test_info['failed']
#             ))
            _logger.debug(
                'Rejecting %s due to filters: '
                'Passed=%s. Failed=%s.',
                url_info.url,
                test_info['passed'],
                test_info['failed']
            )

            return False, 'filters'

    def _add_post_data(self, request):
        if self._url_item.url_record.post_data:
            data = wpull.string.to_bytes(self._url_item.url_record.post_data)
        else:
            data = wpull.string.to_bytes(
                self._processor.fetch_params.post_data
            )

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
            root = self._processor.root_path
            response.body.content_file = Body.new_temp_file(root)

            if self._file_writer_session:
                self._file_writer_session.process_response(response)

            return response

        return factory

    def _handle_response(self, response):
        '''Process the response.'''
        self._url_item.set_value(status_code=response.status_code)

        if self._rich_client_session.redirect_tracker.is_redirect():
            return self._handle_redirect(response)
        elif response.status_code in self._document_codes \
        or self._processor.fetch_params.content_on_error:
            return self._handle_document(response)
        elif response.status_code in self._no_document_codes:
            return self._handle_no_document(response)
        else:
            return self._handle_document_error(response)

    def _handle_document(self, response):
        '''Process a document response.'''
        _logger.debug('Got a document.')

        filename = self._file_writer_session.save_document(response)

        if filename:
            filename = os.path.relpath(filename, self._processor.root_path)

        self._scrape_document(self._request, response)
        self._processor.instances.waiter.reset()
        self._processor.instances.statistics.increment(
            response.body.content_size
        )
        self._url_item.set_status(Status.done, filename=filename)

        return True

    @classmethod
    def parse_url(cls, url, encoding):
        '''Parse and return a URLInfo.

        This function logs a warning if the URL cannot be parsed and returns
        None.
        '''
        try:
            url_info = URLInfo.parse(url, encoding=encoding)
            # FIXME: workaround detection of bad URL unsplit. See issue #132.
            URLInfo.parse(url_info.url, encoding=encoding)
        except ValueError as error:
            _logger.warning(_('Discarding malformed URL ‘{url}’: {error}.')\
                .format(url=url, error=error))
        else:
            return url_info

    def _handle_no_document(self, response):
        '''Callback for when no useful document is received.'''
        self._processor.instances.waiter.reset()
        self._file_writer_session.discard_document(response)
        self._url_item.set_status(Status.skipped)

        return True

    def _handle_document_error(self, response):
        '''Callback for when the document only describes an server error.'''
        self._processor.instances.waiter.increment()
        self._file_writer_session.discard_document(response)
        self._processor.instances.statistics.errors[ServerError] += 1
        self._url_item.set_status(Status.error)

        return True

    def _handle_error(self, error):
        '''Process an error.'''
        self._processor.instances.statistics.errors[type(error)] += 1
        self._processor.instances.waiter.increment()

        if isinstance(error, ConnectionRefused) \
        and not self._processor.fetch_params.retry_connrefused:
            self._url_item.set_status(Status.skipped)
        elif isinstance(error, DNSNotFound) \
        and not self._processor.fetch_params.retry_dns_error:
            self._url_item.set_status(Status.skipped)
        else:
            self._url_item.set_status(Status.error)

        return True

    def _handle_redirect(self, response):
        '''Process a redirect.'''
        self._processor.instances.waiter.reset()
        return False

    def _scrape_document(self, request, response):
        '''Scrape the document for URLs.'''
        demux_info = self._processor.instances\
            .document_scraper.scrape_info(request, response)

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

        if isinstance(scraper, CSSScraper):
            link_type = LinkType.css
        elif isinstance(scraper, HTMLScraper):
            link_type = LinkType.html
        else:
            link_type = None

        inline_urls = scrape_info['inline_urls']
        linked_urls = scrape_info['linked_urls']
        encoding = scrape_info['encoding']

        assert encoding

        inline_url_infos = set()
        linked_url_infos = set()

        for url in inline_urls:
            url_info = self.parse_url(url, encoding)
            if url_info:
                url_record = self._url_item.child_url_record(
                    url_info, inline=True, encoding=encoding
                )
                if self._should_fetch_reason(url_info, url_record)[0]:
                    inline_url_infos.add(url_info)

        for url in linked_urls:
            url_info = self.parse_url(url, encoding)
            if url_info:
                url_record = self._url_item.child_url_record(
                    url_info, encoding=encoding, link_type=link_type
                )
                if self._should_fetch_reason(url_info, url_record)[0]:
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

    def _get_wait_time(self):
        '''Return the wait time.'''
        return self._processor.instances.waiter.get()

    @tornado.gen.coroutine
    def _process_phantomjs(self, request, response):
        '''Process PhantomJS.'''
        if not self._processor.instances.phantomjs_controller:
            return

        if response.status_code != 200:
            return

        if not HTMLReader.is_supported(request=request, response=response):
            return

        _logger.debug('Starting PhantomJS processing.')

        controller = self._processor.instances.phantomjs_controller

        with controller.client.remote() as remote:
            self._hook_phantomjs_logging(remote)

            yield controller.apply_page_size(remote)
            yield remote.call('page.open', request.url_info.url)
            yield remote.wait_page_event('load_finished')
            yield controller.control(remote)

            # FIXME: not sure where the logic should fit in
            if controller._snapshot:
                yield self._take_phantomjs_snapshot(controller, remote)

            content = yield remote.eval('page.content')

        mock_response = self._new_phantomjs_response(response, content)

        self._scrape_document(request, mock_response)

        _logger.debug('Ended PhantomJS processing.')

    def _new_phantomjs_response(self, response, content):
        '''Return a new mock Response with the content.'''
        mock_response = copy.copy(response)

        # tempfile needed for scripts that need a on-disk filename
        mock_response.body.content_file = tempfile.SpooledTemporaryFile(
            max_size=999999999)

        mock_response.body.content_file.write(content.encode('utf-8'))
        mock_response.body.content_file.seek(0)

        mock_response.fields = NameValueRecord()

        for name, value in response.fields.get_all():
            mock_response.fields.add(name, value)

        mock_response.fields['Content-Type'] = 'text/html; charset="utf-8"'

        return mock_response

    def _hook_phantomjs_logging(self, remote):
        '''Set up logging from PhantomJS to Wpull.'''
        def fetch_log(rpc_info):
            _logger.info(
                _('PhantomJS fetching ‘{url}’.')\
                .format(url=rpc_info['request_data']['url'])
            )

        def fetched_log(rpc_info):
            if rpc_info['response']['stage'] != 'end':
                return

            response = rpc_info['response']

            self._processor.instances.statistics.increment(
                response.get('bodySize', 0)
            )

            url = response['url']

            if url.endswith('/WPULLHTTPS'):
                url = url[:-11].replace('http://', 'https://', 1)

            _logger.info(
                _('PhantomJS fetched ‘{url}’: {status_code} {reason}. '
                    'Length: {content_length} [{content_type}].').format(
                    url=url,
                    status_code=response['status'],
                    reason=response['statusText'],
                    content_length=response.get('bodySize'),
                    content_type=response.get('contentType'),
                )
            )

        def fetch_error_log(rpc_info):
            resource_error = rpc_info['resource_error']

            _logger.error(
                _('PhantomJS fetching ‘{url}’ encountered an error: {error}')\
                .format(
                    url=resource_error['url'],
                    error=resource_error['errorString']
                )
            )

        def handle_page_event(rpc_info):
            name = rpc_info['event']

            if name == 'resource_requested':
                fetch_log(rpc_info)
            elif name == 'resource_received':
                fetched_log(rpc_info)
            elif name == 'resource_error':
                fetch_error_log(rpc_info)

        remote.page_event.handle(handle_page_event)

    @tornado.gen.coroutine
    def _take_phantomjs_snapshot(self, controller, remote):
        '''Take HTML and PDF snapshot.'''
        html_path = self._file_writer_session.extra_resource_path(
            '.snapshot.html'
        )
        pdf_path = self._file_writer_session.extra_resource_path(
            '.snapshot.pdf'
        )

        files_to_del = []

        if not html_path:
            temp_file = tempfile.NamedTemporaryFile(
                dir=self._processor.root_path, delete=False, suffix='.html'
            )
            html_path = temp_file.name
            files_to_del.append(html_path)
            temp_file.close()

        if not pdf_path:
            temp_file = tempfile.NamedTemporaryFile(
                dir=self._processor.root_path, delete=False, suffix='.pdf'
            )
            pdf_path = temp_file.name
            files_to_del.append(pdf_path)
            temp_file.close()

        yield controller.snapshot(remote, html_path, pdf_path)

        for filename in files_to_del:
            os.remove(filename)


class PhantomJSController(object):
    '''PhantomJS Page Controller.'''
    def __init__(self, client, wait_time=1.0, num_scrolls=10, snapshot=True,
    warc_recorder=None, viewport_size=(1200, 1920), paper_size=(2400, 3840),
    smart_scroll=True):
        self.client = client
        self._wait_time = wait_time
        self._num_scrolls = num_scrolls
        self._snapshot = snapshot
        self._warc_recorder = warc_recorder
        self._viewport_size = viewport_size
        self._paper_size = paper_size
        self._smart_scroll = smart_scroll
        self._actions = []
        self._action_warc_record = None

    @tornado.gen.coroutine
    def apply_page_size(self, remote):
        '''Apply page size.'''
        yield remote.set(
            'page.viewportSize',
            {'width': self._viewport_size[0], 'height': self._viewport_size[1]}
        )
        yield remote.set(
            'page.paperSize',
            {
                'width': '{0}.px'.format(self._paper_size[0]),
                'height': '{0}.px'.format(self._paper_size[1]),
                'border': '0px'
            }
        )

    @tornado.gen.coroutine
    def control(self, remote):
        '''Scroll the page.'''
        num_scrolls = self._num_scrolls

        if self._smart_scroll:
            is_page_dynamic = yield remote.call('isPageDynamic')

            if not is_page_dynamic:
                num_scrolls = 0

        url = yield remote.eval('page.url')
        total_scroll_count = 0

        for scroll_count in range(num_scrolls):
            _logger.debug('Scrolling page. Count={0}.'.format(scroll_count))

            pre_scroll_counter_values = remote.resource_counter.values()

            scroll_position = yield remote.eval('page.scrollPosition')
            scroll_position['top'] += self._viewport_size[1]

            yield self.scroll_to(remote, 0, scroll_position['top'])

            total_scroll_count += 1

            self._log_action('wait', self._wait_time)
            yield wpull.async.sleep(self._wait_time)

            post_scroll_counter_values = remote.resource_counter.values()

            _logger.debug(
                'Counter values pre={0} post={1}'.format(
                    pre_scroll_counter_values,
                    post_scroll_counter_values
                )
            )

            if post_scroll_counter_values == pre_scroll_counter_values \
            and self._smart_scroll:
                break

        for dummy in range(remote.resource_counter.pending):
            if remote.resource_counter.pending:
                self._log_action('wait', self._wait_time)
                yield wpull.async.sleep(self._wait_time)
            else:
                break

        yield self.scroll_to(remote, 0, 0)

        _logger.info(
            gettext.ngettext(
                'Scrolled page {num} time.',
                'Scrolled page {num} times.',
                total_scroll_count,
            ).format(num=total_scroll_count)
        )

        if self._warc_recorder:
            self._add_warc_action_log(url)

    @tornado.gen.coroutine
    def scroll_to(self, remote, x, y):
        page_down_key = yield remote.eval('page.event.key.PageDown')

        self._log_action('set_scroll_left', x)
        self._log_action('set_scroll_top', y)

        yield remote.set('page.scrollPosition', {'left': x, 'top': y})
        yield remote.set('page.evaluate',
            '''
            function() {{
                if (window) {{
                    window.scrollTo({0}, {1});
                }}
            }}
            '''.format(x, y)
        )
        yield remote.call('page.sendEvent', 'keypress', page_down_key)
        yield remote.call('page.sendEvent', 'keydown', page_down_key)
        yield remote.call('page.sendEvent', 'keyup', page_down_key)

    @tornado.gen.coroutine
    def snapshot(self, remote, html_path=None, render_path=None):
        '''Take HTML and PDF snapshot.'''
        content = yield remote.eval('page.content')
        url = yield remote.eval('page.url')

        if html_path:
            _logger.debug('Saving snapshot to {0}.'.format(html_path))
            dir_path = os.path.abspath(os.path.dirname(html_path))

            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            with open(html_path, 'wb') as out_file:
                out_file.write(content.encode('utf-8'))

            if self._warc_recorder:
                self._add_warc_snapshot(html_path, 'text/html', url)

        if render_path:
            _logger.debug('Saving snapshot to {0}.'.format(render_path))
            yield remote.call('page.render', render_path)

            if self._warc_recorder:
                self._add_warc_snapshot(render_path, 'application/pdf', url)

        raise tornado.gen.Return(content)

    def _add_warc_snapshot(self, filename, content_type, url):
        '''Add the snaphot to the WARC file.'''
        _logger.debug('Adding snapshot record.')

        record = WARCRecord()
        record.set_common_fields('resource', content_type)
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}'\
            .format(wpull.url.quote(url))

        if self._action_warc_record:
            record.fields['WARC-Concurrent-To'] = \
                self._action_warc_record.fields[WARCRecord.WARC_RECORD_ID]

        with open(filename, 'rb') as in_file:
            record.block_file = in_file

            self._warc_recorder.set_length_and_maybe_checksums(record)
            self._warc_recorder.write_record(record)

    def _log_action(self, name, value):
        '''Add a action to the action log.'''
        _logger.debug('Action: {0} {1}'.format(name, value))

        self._actions.append({
            'event': name,
            'value': value,
            'timestamp': time.time(),
        })

    def _add_warc_action_log(self, url):
        '''Add the acton log to the WARC file.'''
        _logger.debug('Adding action log record.')

        log_data = json.dumps(
            {'actions': self._actions},
            indent=4,
        ).encode('utf-8')

        self._action_warc_record = record = WARCRecord()
        record.set_common_fields('metadata', 'application/json')
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}'\
            .format(wpull.url.quote(url))
        record.block_file = io.BytesIO(log_data)

        self._warc_recorder.set_length_and_maybe_checksums(record)
        self._warc_recorder.write_record(record)
