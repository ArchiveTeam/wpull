'''PhantomJS page loading and scrolling.'''
import contextlib
import copy
import gettext
import json
import logging
import os
import tempfile
import io

import namedlist
import trollius
from trollius import From, Return

from wpull.backport.logging import BraceMessage as __
from wpull.document.html import HTMLReader
from wpull.body import Body
from wpull.driver.phantomjs import PhantomJSDriverParams
from wpull.namevalue import NameValueRecord
from wpull.warc import WARCRecord
import wpull.url


PhantomJSParams = namedlist.namedtuple(
    'PhantomJSParamsType', [
        ('snapshot_types', ('html', 'pdf')),
        ('wait_time', 1),
        ('num_scrolls', 10),
        ('smart_scroll', True),
        ('snapshot', True),
        ('viewport_size', (1200, 1920)),
        ('paper_size', (2400, 3840)),
        ('load_time', 900),
        ('custom_headers', {}),
        ('page_settings', {}),
    ]
)
'''PhantomJS parameters

Attributes:
    snapshot_type (list): File types. Accepted are html, pdf, png, gif.
    wait_time (float): Time between page scrolls.
    num_scrolls (int): Maximum number of scrolls.
    smart_scroll (bool): Whether to stop scrolling if number of
        requests & responses do not change.
    snapshot (bool): Whether to take snapshot files.
    viewport_size (tuple): Width and height of the page viewport.
    paper_size (tuple): Width and height of the paper size.
    load_time (float): Maximum time to wait for page load.
    custom_headers (dict): Default HTTP headers.
    page_settings (dict): Page settings.
'''


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class PhantomJSCrashed(Exception):
    '''PhantomJS exited with non-zero code.'''


class PhantomJSCoprocessor(object):
    '''PhantomJS coprocessor.

    Args:
        phantomjs_driver_factory: Callback function that accepts ``params``
            argument and returns
            an instance of :class:`.driver.PhantomJSDrive
        processing_rule (:class:`.processor.rule.ProcessingRule`): Processing
            rule.
        warc_recorder: WARC recorder.
        root_dir (str): Root directory path for temp files.
    '''
    def __init__(self, phantomjs_driver_factory, processing_rule,
                 phantomjs_params,
                 warc_recorder=None, root_path='.'):
        self._phantomjs_driver_factory = phantomjs_driver_factory
        self._processing_rule = processing_rule
        self._phantomjs_params = phantomjs_params
        self._warc_recorder = warc_recorder
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

        self._file_writer_session = file_writer_session

        # FIXME: this is a quick hack for crashes. See #137.
        attempts = int(os.environ.get('WPULL_PHANTOMJS_TRIES', 5))

        for dummy in range(attempts):
            try:
                yield From(self._run_driver(url_item, request, response))
            except trollius.TimeoutError:
                _logger.warning(_('Waiting for page load timed out.'))
                break
            except PhantomJSCrashed as error:
                _logger.exception(__('PhantomJS crashed: {}', error))
            else:
                break
        else:
            _logger.warning(__(
                _('PhantomJS failed to fetch ‘{url}’. I am sorry.'),
                url=request.url_info.url
            ))

    @trollius.coroutine
    def _run_driver(self, url_item, request, response):
        '''Start PhantomJS processing.'''
        _logger.debug('Started PhantomJS processing.')

        session = PhantomJSCoprocessorSession(
            self._phantomjs_driver_factory, self._root_path,
            self._processing_rule, self._file_writer_session,
            request, response,
            url_item, self._phantomjs_params, self._warc_recorder
        )

        with contextlib.closing(session):
            yield From(session.run())

        _logger.debug('Ended PhantomJS processing.')


class PhantomJSCoprocessorSession(object):
    '''PhantomJS coprocessor session.'''
    def __init__(self, phantomjs_driver_factory, root_path,
                 processing_rule, file_writer_session,
                 request, response,
                 url_item, params, warc_recorder):
        self._phantomjs_driver_factory = phantomjs_driver_factory
        self._root_path = root_path
        self._processing_rule = processing_rule
        self._file_writer_session = file_writer_session
        self._request = request
        self._response = response
        self._url_item = url_item
        self._params = params
        self._warc_recorder = warc_recorder
        self._temp_filenames = []

    @trollius.coroutine
    def run(self):
        tempfile.NamedTemporaryFile(prefix='wpull-snp')

        scrape_snapshot_path = self._get_temp_path('phantom', suffix='.html')
        action_log_path = self._get_temp_path('phantom-action', suffix='.txt')
        event_log_path = self._get_temp_path('phantom-event', suffix='.txt')
        snapshot_paths = [scrape_snapshot_path]
        snapshot_paths.extend(self._get_snapshot_paths())
        url = self._url_item.url_record.url

        driver_params = PhantomJSDriverParams(
            url=url,
            snapshot_paths=snapshot_paths,
            wait_time=self._params.wait_time,
            num_scrolls=self._params.num_scrolls,
            smart_scroll=self._params.smart_scroll,
            snapshot=self._params.snapshot,
            viewport_size=self._params.viewport_size,
            paper_size=self._params.paper_size,
            event_log_filename=event_log_path,
            action_log_filename=action_log_path,
            custom_headers=self._params.custom_headers,
            page_settings=self._params.page_settings,
        )

        driver = self._phantomjs_driver_factory(params=driver_params)

        _logger.info(__(
            _('PhantomJS fetching ‘{url}’.'),
            url=url
        ))

        with contextlib.closing(driver):
            yield From(driver.start())

            # FIXME: we don't account that things might be scrolling and
            # downloading so it might not be a good idea to timeout like
            # this
            if self._params.load_time:
                yield From(trollius.wait_for(
                    driver.process.wait(), self._params.load_time
                ))
            else:
                yield From(driver.process.wait())

            if driver.process.returncode != 0:
                raise PhantomJSCrashed(
                    'PhantomJS exited with code {}'
                    .format(driver.process.returncode)
                )

        if self._warc_recorder:
            self._add_warc_action_log(action_log_path, url)
            for path in snapshot_paths:
                self._add_warc_snapshot(path, url)

        _logger.info(__(
            _('PhantomJS fetched ‘{url}’.'),
            url=url
        ))

    def _get_temp_path(self, hint, suffix='.tmp'):
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self._root_path, prefix='wpull-{}'.format(hint), suffix=suffix
        )
        os.close(temp_fd)
        self._temp_filenames.append(temp_path)

        return temp_path

    def _get_snapshot_paths(self, infix='snapshot'):
        for snapshot_type in self._params.snapshot_types or ():
            path = self._file_writer_session.extra_resource_path(
                '.{infix}.{file_type}'
                .format(infix=infix, file_type=snapshot_type)
            )

            if not path:
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=self._root_path, prefix='phnsh',
                    suffix='.{}'.format(snapshot_type)
                )
                os.close(temp_fd)
                path = temp_path
                self._temp_filenames.append(temp_path)

            yield path

    def _add_warc_action_log(self, path, url):
        '''Add the action log to the WARC file.'''
        _logger.debug('Adding action log record.')

        actions = []
        with open(path, 'r', encoding='utf-8', errors='replace') as file:
            for line in file:
                actions.append(json.loads(line))

        log_data = json.dumps(
            {'actions': actions},
            indent=4,
        ).encode('utf-8')

        self._action_warc_record = record = WARCRecord()
        record.set_common_fields('metadata', 'application/json')
        record.fields['WARC-Target-URI'] = 'urn:X-wpull:snapshot?url={0}' \
            .format(wpull.url.percent_encode_query_value(url))
        record.block_file = io.BytesIO(log_data)

        self._warc_recorder.set_length_and_maybe_checksums(record)
        self._warc_recorder.write_record(record)

    def _add_warc_snapshot(self, filename, url):
        '''Add the snaphot to the WARC file.'''
        _logger.debug('Adding snapshot record.')

        extension = os.path.splitext(filename)[1]
        content_type = {
            '.pdf': 'application/pdf',
            '.html': 'text/html',
            '.png': 'image/png',
            '.gif': 'image/gif'
            }[extension]

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

    def _scrape_document(self):
        '''Extract links from the DOM.'''
        mock_response = self._new_mock_response(
            self._response, self._get_temp_path('phantom', '.html')
        )

        self._processing_rule.scrape_document(
            self._request, mock_response, self._url_item
        )

        if mock_response.body:
            mock_response.body.close()

    def _new_mock_response(self, response, file_path):
        '''Return a new mock Response with the content.'''
        mock_response = copy.copy(response)

        mock_response.body = Body(open(file_path, 'rb'))
        mock_response.fields = NameValueRecord()

        for name, value in response.fields.get_all():
            mock_response.fields.add(name, value)

        mock_response.fields['Content-Type'] = 'text/html; charset="utf-8"'

        return mock_response

    def close(self):
        '''Clean up.'''
        for path in self._temp_filenames:
            if os.path.exists(path):
                os.remove(path)
