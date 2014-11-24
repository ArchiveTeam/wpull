# encoding=utf-8
'''PhantomJS coprocessing.'''
import copy
import gettext
import io
import json
import logging
import os.path
import tempfile
import time

import trollius
from trollius import From, Return

from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.document.html import HTMLReader
from wpull.driver.phantomjs import PhantomJSRPCTimedOut
from wpull.namevalue import NameValueRecord
import wpull.url
from wpull.warc import WARCRecord


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class PhantomJSController(object):
    '''PhantomJS Page Controller.'''
    def __init__(self, client, wait_time=1.0, num_scrolls=10, snapshot=True,
                 warc_recorder=None, viewport_size=(1200, 1920),
                 paper_size=(2400, 3840), smart_scroll=True):
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

    @trollius.coroutine
    def apply_page_size(self, remote):
        '''Apply page size.

        Coroutine.
        '''
        yield From(remote.set(
            'page.viewportSize',
            {'width': self._viewport_size[0], 'height': self._viewport_size[1]}
        ))
        yield From(remote.set(
            'page.paperSize',
            {
                'width': '{0}.px'.format(self._paper_size[0]),
                'height': '{0}.px'.format(self._paper_size[1]),
                'border': '0px'
            }
        ))

    @trollius.coroutine
    def control(self, remote):
        '''Scroll the page.

        Coroutine.
        '''
        num_scrolls = self._num_scrolls

        if self._smart_scroll:
            is_page_dynamic = yield From(remote.call('isPageDynamic'))

            if not is_page_dynamic:
                num_scrolls = 0

        url = yield From(remote.eval('page.url'))
        total_scroll_count = 0

        for scroll_count in range(num_scrolls):
            _logger.debug(__('Scrolling page. Count={0}.', scroll_count))

            pre_scroll_counter_values = remote.resource_counter.values()

            scroll_position = yield From(remote.eval('page.scrollPosition'))
            scroll_position['top'] += self._viewport_size[1]

            yield From(self.scroll_to(remote, 0, scroll_position['top']))

            total_scroll_count += 1

            self._log_action('wait', self._wait_time)
            yield From(trollius.sleep(self._wait_time))

            post_scroll_counter_values = remote.resource_counter.values()

            _logger.debug(__(
                'Counter values pre={0} post={1}',
                pre_scroll_counter_values,
                post_scroll_counter_values
            ))

            if post_scroll_counter_values == pre_scroll_counter_values \
               and self._smart_scroll:
                break

        for dummy in range(remote.resource_counter.pending):
            if remote.resource_counter.pending:
                self._log_action('wait', self._wait_time)
                yield From(trollius.sleep(self._wait_time))
            else:
                break

        yield From(self.scroll_to(remote, 0, 0))

        _logger.info(__(
            gettext.ngettext(
                'Scrolled page {num} time.',
                'Scrolled page {num} times.',
                total_scroll_count,
            ), num=total_scroll_count
        ))

        if self._warc_recorder:
            self._add_warc_action_log(url)

    @trollius.coroutine
    def scroll_to(self, remote, x, y):
        '''Scroll the page.

        Coroutine.
        '''
        page_down_key = yield From(remote.eval('page.event.key.PageDown'))

        self._log_action('set_scroll_left', x)
        self._log_action('set_scroll_top', y)

        yield From(remote.set('page.scrollPosition', {'left': x, 'top': y}))
        yield From(remote.set('page.evaluate',
                              '''
                              function() {{
                              if (window) {{
                              window.scrollTo({0}, {1});
                              }}
                              }}
                              '''.format(x, y)))
        yield From(remote.call('page.sendEvent', 'keypress', page_down_key))
        yield From(remote.call('page.sendEvent', 'keydown', page_down_key))
        yield From(remote.call('page.sendEvent', 'keyup', page_down_key))

    @trollius.coroutine
    def snapshot(self, remote, html_path=None, render_path=None):
        '''Take HTML and PDF snapshot.

        Coroutine.
        '''
        content = yield From(remote.eval('page.content'))
        url = yield From(remote.eval('page.url'))

        if html_path:
            _logger.debug(__('Saving snapshot to {0}.', html_path))
            dir_path = os.path.abspath(os.path.dirname(html_path))

            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            with open(html_path, 'wb') as out_file:
                out_file.write(content.encode('utf-8'))

            if self._warc_recorder:
                self._add_warc_snapshot(html_path, 'text/html', url)

        if render_path:
            _logger.debug(__('Saving snapshot to {0}.', render_path))
            yield From(remote.call('page.render', render_path))

            if self._warc_recorder:
                self._add_warc_snapshot(render_path, 'application/pdf', url)

        raise Return(content)

    def _add_warc_snapshot(self, filename, content_type, url):
        '''Add the snaphot to the WARC file.'''
        _logger.debug('Adding snapshot record.')

        record = WARCRecord()
        record.set_common_fields('resource', content_type)
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}'\
            .format(wpull.url.percent_encode_query_value(url))

        if self._action_warc_record:
            record.fields['WARC-Concurrent-To'] = \
                self._action_warc_record.fields[WARCRecord.WARC_RECORD_ID]

        with open(filename, 'rb') as in_file:
            record.block_file = in_file

            self._warc_recorder.set_length_and_maybe_checksums(record)
            self._warc_recorder.write_record(record)

    def _log_action(self, name, value):
        '''Add a action to the action log.'''
        _logger.debug(__('Action: {0} {1}', name, value))

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
            .format(wpull.url.percent_encode_query_value(url))
        record.block_file = io.BytesIO(log_data)

        self._warc_recorder.set_length_and_maybe_checksums(record)
        self._warc_recorder.write_record(record)


class WebProcessorSessionMixin(object):
    '''This class is just temporary while things are rewritten out of
    web processor.'''

    @trollius.coroutine
    def _process_phantomjs(self, request, response):
        '''Process PhantomJS.

        Coroutine.
        '''
        if not self._processor.instances.phantomjs_controller:
            return

        if response.status_code != 200:
            return

        if not HTMLReader.is_supported(request=request, response=response):
            return

        _logger.debug('Starting PhantomJS processing.')

        controller = self._processor.instances.phantomjs_controller

        attempts = int(os.environ.get('WPULL_PHANTOMJS_TRIES', 5))
        content = None

        for dummy in range(attempts):
            # FIXME: this is a quick hack for handling time outs. See #137.
            try:
                with controller.client.remote() as remote:
                    self._hook_phantomjs_logging(remote)

                    yield From(controller.apply_page_size(remote))
                    yield From(remote.call('page.open', request.url_info.url))
                    yield From(remote.wait_page_event('load_finished'))
                    yield From(controller.control(remote))

                    # FIXME: not sure where the logic should fit in
                    if controller._snapshot:
                        yield From(self._take_phantomjs_snapshot(controller, remote))

                    content = yield From(remote.eval('page.content'))
            except PhantomJSRPCTimedOut:
                _logger.exception('PhantomJS timed out.')
            else:
                break

        if content is not None:
            mock_response = self._new_phantomjs_response(response, content)

            self._processing_rule.scrape_document(request, mock_response, self._url_item)

            self._close_instance_body(mock_response)

            _logger.debug('Ended PhantomJS processing.')
        else:
            _logger.warning(__(
                _('PhantomJS failed to fetch ‘{url}’. I am sorry.'),
                url=request.url_info.url
            ))

    def _new_phantomjs_response(self, response, content):
        '''Return a new mock Response with the content.'''
        mock_response = copy.copy(response)

        mock_response.body = Body(
            wpull.body.new_temp_file(
                self._processor.root_path, hint='phjs_resp'
            ))
        self._temp_files.add(mock_response.body)

        mock_response.body.write(content.encode('utf-8'))
        mock_response.body.seek(0)

        mock_response.fields = NameValueRecord()

        for name, value in response.fields.get_all():
            mock_response.fields.add(name, value)

        mock_response.fields['Content-Type'] = 'text/html; charset="utf-8"'

        return mock_response

    def _hook_phantomjs_logging(self, remote):
        '''Set up logging from PhantomJS to Wpull.'''
        def fetch_log(rpc_info):
            _logger.info(__(
                _('PhantomJS fetching ‘{url}’.'),
                url=rpc_info['request_data']['url']
            ))

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

            _logger.info(__(
                _('PhantomJS fetched ‘{url}’: {status_code} {reason}. '
                  'Length: {content_length} [{content_type}].'),
                url=url,
                status_code=response['status'],
                reason=response['statusText'],
                content_length=response.get('bodySize'),
                content_type=response.get('contentType'),
                ))

        def fetch_error_log(rpc_info):
            resource_error = rpc_info['resource_error']

            _logger.error(__(
                _('PhantomJS fetching ‘{url}’ encountered an error: {error}'),
                url=resource_error['url'],
                error=resource_error['errorString']
            ))

        def handle_page_event(rpc_info):
            name = rpc_info['event']

            if name == 'resource_requested':
                fetch_log(rpc_info)
            elif name == 'resource_received':
                fetched_log(rpc_info)
            elif name == 'resource_error':
                fetch_error_log(rpc_info)

        remote.page_observer.add(handle_page_event)

    @trollius.coroutine
    def _take_phantomjs_snapshot(self, controller, remote):
        '''Take HTML and PDF snapshot.

        Coroutine.
        '''
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

        try:
            yield From(controller.snapshot(remote, html_path, pdf_path))
        finally:
            for filename in files_to_del:
                if os.path.exists(filename):
                    os.remove(filename)
