# encoding=utf-8
import gettext
import logging
import tornado.gen
import toro
import traceback

from wpull.database import Status, NotFound
from wpull.errors import ExitStatus, ServerError, ConnectionRefused, DNSNotFound
from wpull.http import NetworkError, ProtocolError
from wpull.url import URLInfo
import wpull.util


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Engine(object):
    ERROR_CODE_MAP = {
        NetworkError: ExitStatus.network_failure,
        ProtocolError: ExitStatus.protocol_error,
        ValueError: ExitStatus.parser_error,
        ServerError: ExitStatus.server_error,
        OSError: ExitStatus.file_io_error,
        IOError: ExitStatus.file_io_error,
        ConnectionRefused: ExitStatus.network_failure,
        DNSNotFound: ExitStatus.network_failure,
    }

    def __init__(self, url_table, request_client, processor, concurrent=1):
        self._url_table = url_table
        self._request_client = request_client
        self._processor = processor
        self._worker_semaphore = toro.BoundedSemaphore(concurrent)
        self._done_event = toro.Event()
        self._concurrent = concurrent
        self._num_worker_busy = 0
        self._exit_code = 0

    @tornado.gen.coroutine
    def __call__(self):
        self._release_in_progress()
        self._run_workers()

        yield self._done_event.wait()

        self._compute_exit_code_from_stats()
        self._processor.close()
        self._print_stats()
        self._request_client.close()
        raise tornado.gen.Return(self._exit_code)

    def _release_in_progress(self):
        _logger.debug('Release in-progress.')
        self._url_table.release()

    @tornado.gen.coroutine
    def _run_workers(self):
        while True:
            yield self._worker_semaphore.acquire()
            self._process_input()

    def _get_next_url_record(self):
        _logger.debug('Get next URL todo.')

        try:
            url_record = self._url_table.get_and_update(
                Status.todo, new_status=Status.in_progress)
        except NotFound:
            url_record = None

        if not url_record:
            try:
                _logger.debug('Get next URL error.')
                url_record = self._url_table.get_and_update(
                    Status.error, new_status=Status.in_progress)
            except NotFound:
                url_record = None

        return url_record

    @tornado.gen.coroutine
    def _process_input(self):
        try:
            while True:
                url_record = self._get_next_url_record()

                if not url_record:
                    # TODO: need better check if we are done
                    if self._num_worker_busy == 0:
                        self._stop()
                    yield wpull.util.sleep(1.0)
                else:
                    break

            self._num_worker_busy += 1

            url_info = URLInfo.parse(url_record.url)

            with self._processor.session() as session:
                while True:
                    reprocess = yield self._process_session(
                        session, url_record, url_info)
                    if not reprocess:
                        break

            _logger.debug('Table size: {0}.'.format(self._url_table.count()))
        except Exception as error:
            # FIXME: figure out why tornado doesn't catch the errors for us
            traceback.print_exc()
            _logger.exception('Fatal exception.')
            self._update_exit_code_from_error(error)
            self._stop()

        self._num_worker_busy -= 1
        self._worker_semaphore.release()

    @tornado.gen.coroutine
    def _process_session(self, session, url_record, url_info):
        _logger.debug('Begin session for {0} {1}'.format(url_record, url_info))
        request = session.new_request(url_record, url_info)

        if not request:
            self._skip_url(url_record.url)
            return

        _logger.info(_('Fetching ‘{url}’.').format(url=request.url_info.url))

        try:
            response = yield self._request_client.fetch(request,
                response_factory=session.response_factory())
        except (NetworkError, ProtocolError) as error:
            _logger.error(
                _('Fetching ‘{url}’ encountered an error: {error}')\
                    .format(url=url_info.url, error=error)
            )
            session.handle_error(error)
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
            session.handle_response(response)

        wait_time = session.wait_time()

        if wait_time:
            _logger.debug('Sleeping {0}.'.format(wait_time))
            yield wpull.util.sleep(wait_time)

        # TODO: need status_code for setting its value in the table

        if session.url_record_status():
            self._set_url_status(url_record.url, session.url_record_status())
            self._add_urls_from_session(url_record, session)
        else:
            # Retry request for things such as redirects
            _logger.debug('Retrying request.')
            raise tornado.gen.Return(True)

    def _skip_url(self, url):
        _logger.debug(_('Skipping ‘{url}’.').format(url=url))
        self._url_table.update(url, status=Status.skipped)

    def _set_url_status(self, url, status):
        _logger.debug('Marking URL {0} status {1}.'.format(url, status))
        self._url_table.update(url, increment_try_count=True, status=status)

    def _add_urls_from_session(self, url_record, session):
        inline_url_infos = session.inline_url_infos()
        inline_urls = tuple([info.url for info in inline_url_infos])
        _logger.debug('Adding inline URLs {0}'.format(inline_urls))
        self._url_table.add(
            inline_urls,
            inline=1,
            level=url_record.level + 1,
            referrer=url_record.url,
            top_url=url_record.top_url or url_record.url
        )
        linked_url_infos = session.linked_url_infos()
        linked_urls = tuple([info.url for info in linked_url_infos])
        _logger.debug('Adding linked URLs {0}'.format(linked_urls))
        self._url_table.add(
            linked_urls,
            level=url_record.level + 1,
            referrer=url_record.url,
            top_url=url_record.top_url or url_record.url
        )

    def _stop(self):
        self._done_event.set()

    def _update_exit_code_from_error(self, error):
        for error_type, exit_code in self.ERROR_CODE_MAP.items():
            if isinstance(error, error_type):
                self._update_exit_code(exit_code)
                break
        else:
            self._update_exit_code(ExitStatus.generic_error)

    def _update_exit_code(self, code):
        if code:
            if self._exit_code:
                self._exit_code = min(self._exit_code, code)
            else:
                self._exit_code = code

    def _compute_exit_code_from_stats(self):
        for error_type in self._processor.statistics.errors:
            exit_code = self.ERROR_CODE_MAP.get(error_type)
            if exit_code:
                self._update_exit_code(exit_code)

    def _print_stats(self):
        stats = self._processor.statistics
        time_length = stats.stop_time - stats.start_time

        _logger.info(_('FINISHED.'))
        _logger.info(_('Time length: {time:.1} seconds.')\
            .format(time=time_length))
        _logger.info(_('Downloaded: {num_files} files, {total_size} bytes.')\
            .format(num_files=stats.files, total_size=stats.size))
        _logger.info(_('Exiting with status {0}.').format(self._exit_code))
