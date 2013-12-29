import logging
import tornado.gen
import toro
import traceback

from wpull.database import Status, NotFound
from wpull.errors import ExitStatus, ServerError
from wpull.http import NetworkError, ProtocolError
from wpull.url import URLInfo
import wpull.util


_logger = logging.getLogger(__name__)


class Engine(object):
    ERROR_CODE_MAP = {
        NetworkError: ExitStatus.network_failure,
        ProtocolError: ExitStatus.protocol_error,
        ValueError: ExitStatus.parser_error,
        ServerError: ExitStatus.server_error,
        OSError: ExitStatus.file_io_error,
        IOError: ExitStatus.file_io_error,
    }

    def __init__(self, url_table, http_client, processor, recorder=None,
    concurrent=1):
        self._url_table = url_table
        self._http_client = http_client
        self._processor = processor
        self._recorder = recorder
        self._worker_semaphore = toro.BoundedSemaphore(concurrent)
        self._done_event = toro.Event()
        self._concurrent = concurrent
        self._num_worker_busy = 0
        self._exit_code = 0

    @tornado.gen.coroutine
    def __call__(self):
        self._run_workers()

        yield self._done_event.wait()
        self._compute_exit_code_from_stats()
        exit_code = self._exit_code
        _logger.info('Exiting with status {0}.'.format(exit_code))
        raise tornado.gen.Return(exit_code)

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

        # TODO: return in_progress items by keeping track of them in
        # a variable. for resuming when the process is killed.

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
            # TODO: figure out why tornado doesn't catch the errors for us
            traceback.print_exc()
            self._update_exit_code_from_error(error)
            self._stop()

        self._num_worker_busy -= 1
        self._worker_semaphore.release()

    @tornado.gen.coroutine
    def _process_session(self, session, url_record, url_info):
        _logger.debug('Begin session for {0} {1}'.format(url_record, url_info))
        request = session.new_request(url_record, url_info)

        if request:
            _logger.info('Fetching {url}.'.format(url=request.url_info.url))

            try:
                response = yield self._http_client.fetch(
                    request, recorder=self._recorder)
            except (NetworkError, ProtocolError) as error:
                _logger.exception('Fetch error.')
                status = session.accept_response(None, error)
            else:
                _logger.info(
                    'Fetched {url}: {status_code} {reason}.'.format(
                        url=request.url_info.url,
                        status_code=response.status_code,
                        reason=response.status_reason
                    )
                )
                status = session.accept_response(response)

            wait_time = session.wait_time()

            if wait_time:
                _logger.debug('Sleeping {0}.'.format(wait_time))
                yield wpull.util.sleep(wait_time)

            if status is None:
                # Retry request for things such as redirects
                _logger.debug('Retrying request.')
                raise tornado.gen.Return(True)

            _logger.debug(
                'Marking URL {0} status {1}.'.format(url_record.url, status))
            self._url_table.update(
                url_record.url,
                increment_try_count=True,
                status=status
            )

            inline_urls = session.get_inline_urls()
            _logger.debug('Adding inline URLs {0}'.format(inline_urls))
            self._url_table.add(
                inline_urls,
                inline=1,
                level=url_record.level + 1
            )
            linked_urls = session.get_linked_urls()
            _logger.debug('Adding linked URLs {0}'.format(linked_urls))
            self._url_table.add(
                linked_urls,
                level=url_record.level + 1
            )
        else:
            _logger.debug('Skipping URL {0}.'.format(url_info.url))
            self._url_table.update(url_record.url, status=Status.skipped)

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
