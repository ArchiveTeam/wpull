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
from wpull.driver.resource import PhantomJSResourceTracker
from wpull.driver.scroller import Scroller
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


        # if self._smart_scroll:
        #     is_page_dynamic = yield From(remote.call('isPageDynamic'))
        #
        #     if not is_page_dynamic:
        #         num_scrolls = 0

        # url = yield From(remote.eval('page.url'))

        # for dummy in range(remote.resource_counter.pending):
        #     if remote.resource_counter.pending:
        #         self._log_action('wait', self._wait_time)
        #         yield From(trollius.sleep(self._wait_time))
        #     else:
        #         break


        # if self._warc_recorder:
        #     self._add_warc_action_log(url)



class PhantomJSCoprocessor(object):
    '''PhantomJS coprocessor.'''
    def __init__(self, phantomjs_pool, processing_rule, statistics, snapshot_types=('html', 'pdf'), root_path='.'):
        self._phantomjs_pool = phantomjs_pool
        self._processing_rule = processing_rule
        self._statistics = statistics
        self._snapshot_types = snapshot_types
        self._root_path = root_path

        self._file_writer_session = None

    @trollius.coroutine
    def process(self, url_item, request, response, file_writer_session):
        '''Process PhantomJS.

        Coroutine.
        '''
        if response.status_code != 200:
            return

        if not HTMLReader.is_supported(request=request, response=response):
            return

        _logger.debug('Starting PhantomJS processing.')

        attempts = int(os.environ.get('WPULL_PHANTOMJS_TRIES', 5))
        content = None

        for dummy in range(attempts):
            # FIXME: this is a quick hack for handling time outs. See #137.
            try:
                with self._phantomjs_pool.session() as driver:
                    session = PhantomJSCoprocessorSession()

                    yield From(session.open_url(request.url_info.url))
                    yield From(session.scroll())
                    yield From(session.wait_for_load())

                    for snapshot_type in self._snapshot_types or ():
                        yield From(session.take_snapshot(snapshot_type, ))

            except PhantomJSRPCTimedOut:
                _logger.exception('PhantomJS timed out.')
            else:
                break

        if content is not None:
            mock_response = self._new_phantomjs_response(response, content)

            self._processing_rule.scrape_document(request, mock_response, url_item)

            if mock_response.body:
                mock_response.body.close()

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
                self._root_path, hint='phjs_resp'
            ))

        mock_response.body.write(content.encode('utf-8'))
        mock_response.body.seek(0)

        mock_response.fields = NameValueRecord()

        for name, value in response.fields.get_all():
            mock_response.fields.add(name, value)

        mock_response.fields['Content-Type'] = 'text/html; charset="utf-8"'

        return mock_response


class PhantomJSCoprocessorSession(object):
    def __init__(self, driver, fetch_rule, result_rule, root_path, warc_recorder, scroller_factory):
        self._driver = driver
        self._fetch_rule = fetch_rule
        self._result_rule = result_rule
        self._root_path = root_path
        self._warc_recorder = warc_recorder
        self._scroller = scroller_factory()

        self._resource_tracker = PhantomJSResourceTracker()
        self._scroller.action_callback = self._log_action
        self._actions = []

    @trollius.coroutine
    def open_url(self, url):
        pass

    @trollius.coroutine
    def scroll(self):
        pass

    @trollius.coroutine
    def wait_for_load(self):
        pass

    def resource_requested_cb(self, message):
        request_data = message['request_data']
        should_fetch = self._fetch_rule.check_generic_request()[0]

        if should_fetch:
            url = request_data['url']

            _logger.info(__(
                _('PhantomJS fetching ‘{url}’.'),
                url=url
            ))

            self._resource_tracker.process_request(request_data)

            if url.startswith('https://'):
                new_url = '{}/WPULLHTTPS'.format(url)
                return new_url

        else:
            return 'abort'

    def resource_received_cb(self, message):
        response = message['response']

        self._resource_tracker.process_response(response)

        if response['stage'] != 'end':
            return

        self._result_rule.handle_document(adsfasdfa,asdfsdf)

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

    def resource_error_cb(self, message):
        resource_error = message['resource_error']

        self._resource_tracker.process_error(resource_error)

        _logger.error(__(
            _('PhantomJS fetching ‘{url}’ encountered an error: {error}'),
            url=resource_error['url'],
            error=resource_error['errorString']
        ))

        self._result_rule.handle_error(asdfasdf, asdfsadfasdf)

    def resource_timeout_cb(self, message):
        request = message['request']

        self._resource_tracker.process_error(request)

        _logger.error(__(
            _('PhantomJS fetching ‘{url}’ encountered an error: {error}'),
            url=request['url'],
            error=request['errorString']
        ))

        self._result_rule.handle_error(asdfasdf, asdfsadfasdf)

    def error_cb(self, message):
        _logger.error(__(
            _('PhantomJSError: {message} {trace}'),
            message=message['message'],
            trace=message['trace']
        ))


    @trollius.coroutine
    def take_snapshot(self, snapshot_type, file_writer_session, infix='snapshot'):
        '''Take HTML, PDF, or PNG snapshot.

        The behavior of PNG image dimension exceeding PNG limitations is
        undefined. PhantomJS probably crashes.

        Coroutine.
        '''
        assert snapshot_type, snapshot_type
        assert infix, infix

        path = file_writer_session.extra_resource_path(
            '.{infix}.{file_type}'.format(infix=infix, file_type=snapshot_type)
        )

        if not path:
            temp_file, temp_path = tempfile.mkstemp(
                dir=self._root_path, prefix='phnsh',
                suffix='.{}'.format(snapshot_type)
            )
            temp_file.close()
            path = temp_path
        else:
            temp_path = None

        try:
            yield From(self._driver.snapshot(path))
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        if self._warc_recorder:
            mime_type = {
                'pdf': 'application/pdf',
                'html': 'text/html',
                'png': 'image/png',
                }[snapshot_type]

            self._add_warc_snapshot(path, mime_type, url)

    def _add_warc_snapshot(self, filename, content_type, url):
        '''Add the snaphot to the WARC file.'''
        _logger.debug('Adding snapshot record.')

        record = WARCRecord()
        record.set_common_fields('resource', content_type)
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}' \
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
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}' \
            .format(wpull.url.percent_encode_query_value(url))
        record.block_file = io.BytesIO(log_data)

        self._warc_recorder.set_length_and_maybe_checksums(record)
        self._warc_recorder.write_record(record)
