# encoding=utf-8
'''Item queue management and processing.'''
import datetime
import gettext
import logging

import tornado.gen
import toro

import wpull.actor
from wpull.async import AdjustableSemaphore
import wpull.async
from wpull.database import NotFound
from wpull.errors import (ExitStatus, ServerError, ConnectionRefused, DNSNotFound,
    SSLVerficationError, ProtocolError, NetworkError)
from wpull.item import Status, URLItem
import wpull.string
from wpull.url import URLInfo


try:
    from collections import OrderedDict
except ImportError:
    from wpull.backport.collections import OrderedDict

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Engine(object):
    '''Manages and processes item.

    Args:
        url_table (:class:`.database.BaseURLTable`): A table of URLs to
            be processed.
        processor (:class:`.processor.BaseProcessor`): A processor that
            will do things to finish an item.
        statistics (:class:`.stats.Statistics`): Information needed to
            compute the exit status.
        concurrent (int): The number of items to process at once.

    The engine is described like the following:

    1. Get an "todo" item from the table. If none, skip to step 4.
    2. Ask the processor to process the item.
    3. Go to step 1.
    4. Get an "error" item from the table. If none, skip to step 7.
    5. Ask the processor to process the item.
    6. Go to step 4.
    7. Stop.

    In the context of Wpull, URLs are the central part of items.
    '''
    ERROR_CODE_MAP = OrderedDict([
        (ServerError, ExitStatus.server_error),
        (ProtocolError, ExitStatus.protocol_error),
        (SSLVerficationError, ExitStatus.ssl_verification_error),
        (DNSNotFound, ExitStatus.network_failure),
        (ConnectionRefused, ExitStatus.network_failure),
        (NetworkError, ExitStatus.network_failure),
        (OSError, ExitStatus.file_io_error),
        (IOError, ExitStatus.file_io_error),
        (ValueError, ExitStatus.parser_error),
    ])
    '''Mapping of error types to exit status.'''

    def __init__(self, url_table, processor, statistics,
    concurrent=1):
        self._url_table = url_table
        self._processor = processor
        self._statistics = statistics
        self._worker_semaphore = AdjustableSemaphore(concurrent)
        self._done_event = toro.Event()
        self._num_worker_busy = 0
        self._exit_code = 0
        self._stopping = False
        self.stop_event = wpull.actor.Event()

    @property
    def concurrent(self):
        '''The concurrency value.'''
        return self._worker_semaphore.max

    def set_concurrent(self, value):
        self._worker_semaphore.set_max(value)

    @tornado.gen.coroutine
    def __call__(self):
        '''Run the engine.

        This function will clear any items marked as in-progress, start up
        the workers, and loop until a stop is requested.

        Returns:
            int: An integer describing the exit status.

            .. seealso:: :class:`.errors.ExitStatus`
        '''
        self._statistics.start()
        self._release_in_progress()
        self._run_workers()

        yield self._done_event.wait()

        self._compute_exit_code_from_stats()

        if self._exit_code == ExitStatus.ssl_verification_error:
            self._print_ssl_error()

        self._statistics.stop()
        self._print_stats()
        self._processor.close()
        self._url_table.close()
        self.stop_event.fire()

        raise tornado.gen.Return(self._exit_code)

    def _release_in_progress(self):
        '''Release any items in progress.'''
        _logger.debug('Release in-progress.')
        self._url_table.release()

    @tornado.gen.coroutine
    def _run_workers(self):
        '''Start the worker tasks.'''
        while not self._stopping:
            yield self._worker_semaphore.acquire()

            tornado.ioloop.IOLoop.current().add_future(
                self._process_input(),
                lambda future: future.result(),
            )

    def _get_next_url_record(self):
        '''Return the next available URL from the URL table.

        This function will return items marked as "todo" and then items
        marked as "error". As a consequence, items experiencing errors will
        be done last.

        Returns:
            :class:`.item.URLRecord`.
        '''
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

        _logger.debug('Return record {0}.'.format(url_record))

        return url_record

    @tornado.gen.coroutine
    def _process_input(self):
        '''Get an item and process it.

        If processing an item encounters an error, :func:`stop` is called.

        Contract: This function will release the ``_worker_semaphore``.
        '''
        try:
            while True:
                # Poll for an item
                if not self._stopping:
                    url_record = self._get_next_url_record()
                else:
                    url_record = None

                if not url_record:
                    # TODO: need better check if we are done
                    if self._num_worker_busy == 0:
                        self.stop(force=True)
                        self._worker_semaphore.release()

                        return

                    yield wpull.async.sleep(1.0)
                else:
                    break

            self._num_worker_busy += 1

            url_encoding = url_record.url_encoding or 'utf8'
            url_info = URLInfo.parse(url_record.url, encoding=url_encoding)
            url_item = URLItem(self._url_table, url_info, url_record)

            yield self._process_url_item(url_item)

            assert url_item.is_processed

            self._statistics.mark_done(url_info)

        except Exception as error:
            _logger.exception('Fatal exception.')
            self._update_exit_code_from_error(error)
            self.stop(force=True)

        if self._statistics.is_quota_exceeded:
            _logger.debug('Stopping due to quota.')
            self.stop()

        self._num_worker_busy -= 1
        self._worker_semaphore.release()

    @tornado.gen.coroutine
    def _process_url_item(self, url_item):
        '''Process an item.

        Args:
            url_item (:class:`.item.URLItem`): The item to process.

        This function calls :meth:`.processor.BaseProcessor.process`.
        '''
        _logger.debug('Begin session for {0} {1}.'.format(
            url_item.url_record, url_item.url_info))

        yield self._processor.process(url_item)

        _logger.debug('End session for {0} {1}.'.format(
            url_item.url_record, url_item.url_info))

    def stop(self, force=False):
        '''Stop the engine.

        Args:
            force (bool): If ``True``, don't wait for Sessions to finish and
            stop the Engine immediately. If ``False``, the Engine will wait
            for all workers to finish.
        '''
        _logger.debug('Stopping. force={0}'.format(force))

        self._stopping = True

        if force:
            self._done_event.set()

    def _update_exit_code_from_error(self, error):
        '''Set the exit code based on the error type.

        Args:
            error (:class:`Exception`): An exception instance.
        '''
        for error_type, exit_code in self.ERROR_CODE_MAP.items():
            if isinstance(error, error_type):
                self._update_exit_code(exit_code)
                break
        else:
            self._update_exit_code(ExitStatus.generic_error)

    def _update_exit_code(self, code):
        '''Set the exit code if it is serious than before.

        Args:
            code (int): The exit code.
        '''
        if code:
            if self._exit_code:
                self._exit_code = min(self._exit_code, code)
            else:
                self._exit_code = code

    def _compute_exit_code_from_stats(self):
        '''Set the current exit code based on the Statistics.'''
        for error_type in self._statistics.errors:
            exit_code = self.ERROR_CODE_MAP.get(error_type)
            if exit_code:
                self._update_exit_code(exit_code)

    def _print_stats(self):
        '''Log the final statistics to the user.'''
        stats = self._statistics
        time_length = datetime.timedelta(
            seconds=int(stats.stop_time - stats.start_time)
        )
        file_size = wpull.string.format_size(stats.size)

        if stats.bandwidth_meter.num_samples:
            speed_size_str = wpull.string.format_size(
                stats.bandwidth_meter.speed()
            )
        else:
            speed_size_str = _('-- B')

        _logger.info(_('FINISHED.'))
        _logger.info(
            _(
                'Duration: {preformatted_timedelta}. '
                'Speed: {preformatted_speed_size}/s.'
            ).format(
                preformatted_timedelta=time_length,
                preformatted_speed_size=speed_size_str,
            )
        )
        _logger.info(
            gettext.ngettext(
                'Downloaded: {num_files} file, {preformatted_file_size}.',
                'Downloaded: {num_files} files, {preformatted_file_size}.',
                stats.files
            ).format(
                num_files=stats.files,
                preformatted_file_size=file_size
            )
        )

        if stats.is_quota_exceeded:
            _logger.info(_('Download quota exceeded.'))

        _logger.info(_('Exiting with status {0}.').format(self._exit_code))

    def _print_ssl_error(self):
        '''Print an invalid SSL certificate warning.'''
        _logger.info(_('A SSL certificate could not be verified.'))
        _logger.info(_('To ignore and proceed insecurely, '
            'use ‘--no-check-certificate’.'))
