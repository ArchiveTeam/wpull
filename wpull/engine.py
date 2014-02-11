# encoding=utf-8
'''Item processing and management.'''
import datetime
import gettext
import logging
import tornado.gen
import toro

import wpull.actor
from wpull.database import Status, NotFound
from wpull.errors import (ExitStatus, ServerError, ConnectionRefused, DNSNotFound,
    SSLVerficationError)
from wpull.http import NetworkError, ProtocolError
from wpull.url import URLInfo
import wpull.util


try:
    from collections import OrderedDict
except ImportError:
    from wpull.backport.collections import OrderedDict

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Engine(object):
    '''Manages and processes items.

    Args:
        url_table (BaseURLTable): An instance of
            :class:`.database.BaseURLTable` which contains the URLs to process.
        processor (BaseProcessor): An instance of
            :class:`.processor.BaseProcessor` that will decide what to do with
            the items.
        statistics (Statistics): An instance of :class:`.stats.Statistics`
            which contains information needed to compute the exit status.
        concurrent (int): The number of items to process at once.

    The engine is described like the following:

    1. Get an item from the table. In the context of Wpull, URLs are the
       central part of items. If there are no items, stop.
    2. Ask the processor to process the item.
    3. Go to step 1.
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
        self._worker_semaphore = toro.BoundedSemaphore(concurrent)
        self._done_event = toro.Event()
        self._concurrent = concurrent
        self._num_worker_busy = 0
        self._exit_code = 0
        self._stopping = False
        self.stop_event = wpull.actor.Event()

    @tornado.gen.coroutine
    def __call__(self):
        '''Run the engine.

        This function will clear any items marked as in-progress, start up
        the workers, and loop until a stop is requested.

        Returns:
            int: An integer describing the exit status.

            :seealso: :class:`.errors.ExitStatus`
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
        while True:
            yield self._worker_semaphore.acquire()
            self._process_input()

    def _get_next_url_record(self):
        '''Return the next available URL from the URL table.

        This function will return items marked as "todo" and then items
        marked as "error". As a consequence, items experiencing errors will
        be done last.

        Returns:
            URLRecord: An instance of :class:`.database.URLRecord`.
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
        '''Loop and process until there are no more items to process.

        If processing an item encounters an error :func:`stop` is called.
        '''
        try:
            while True:
                if not self._stopping:
                    url_record = self._get_next_url_record()
                else:
                    url_record = None

                if not url_record:
                    # TODO: need better check if we are done
                    if self._num_worker_busy == 0:
                        self.stop(force=True)
                    yield wpull.util.sleep(1.0)
                else:
                    break

            self._num_worker_busy += 1

            url_encoding = url_record.url_encoding or 'utf8'
            url_info = URLInfo.parse(url_record.url, encoding=url_encoding)
            url_item = URLItem(self._url_table, url_info, url_record)

            yield self._process_url_item(url_item)

            assert url_item.is_processed

        except Exception as error:
            _logger.exception('Fatal exception.')
            self._update_exit_code_from_error(error)
            self.stop(force=True)

        self._num_worker_busy -= 1
        self._worker_semaphore.release()

    @tornado.gen.coroutine
    def _process_url_item(self, url_item):
        '''Process a :class:`URLItem`.

        This function calls :func:`.processor.BaseProcessor.process`.
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
        '''Set the exit code based on the error type.'''
        for error_type, exit_code in self.ERROR_CODE_MAP.items():
            if isinstance(error, error_type):
                self._update_exit_code(exit_code)
                break
        else:
            self._update_exit_code(ExitStatus.generic_error)

    def _update_exit_code(self, code):
        '''Set the exit code if it is serious than before.'''
        if code:
            if self._exit_code:
                self._exit_code = min(self._exit_code, code)
            else:
                self._exit_code = code

    def _compute_exit_code_from_stats(self):
        '''Set the exit code based on the statistics.'''
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
        file_size = wpull.util.format_size(stats.size)

        _logger.info(_('FINISHED.'))
        _logger.info(
            _('Time length: {preformatted_timedelta}.')\
                .format(preformatted_timedelta=time_length))
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
        _logger.info(_('Exiting with status {0}.').format(self._exit_code))

    def _print_ssl_error(self):
        '''Print an invalid SSL certificate warning.'''
        _logger.info(_('A SSL certificate could not be verified.'))
        _logger.info(_('To ignore and proceed insecurely, '
            'use ‘--no-check-certificate’.'))


class URLItem(object):
    '''Item for a URL that needs to processed.'''
    def __init__(self, url_table, url_info, url_record):
        self._url_table = url_table
        self._url_info = url_info
        self._url_record = url_record
        self._url = self._url_record.url
        self._processed = False
        self._try_count_incremented = False

    @property
    def url_info(self):
        '''Return the :class:`.url.URLInfo`.'''
        return self._url_info

    @property
    def url_record(self):
        '''Return the :class:`.database.URLRecord`.'''
        return self._url_record

    @property
    def url_table(self):
        '''Return the :class:`.database.URLTable`.'''
        return self._url_table

    @property
    def is_processed(self):
        '''Return whether the item has been processed.'''
        return self._processed

    def skip(self):
        '''Mark the item as processed without download.'''
        _logger.debug(_('Skipping ‘{url}’.').format(url=self._url))
        self._url_table.update(self._url, status=Status.skipped)

        self._processed = True

    def set_status(self, status, increment_try_count=True):
        '''Mark the item with the given status.

        Args:
            status (Status): a value from :class:`.database.Status`
            increment_try_count (bool): if True, increment the ``try_count``
                value
        '''
        assert not self._try_count_incremented

        if increment_try_count:
            self._try_count_incremented = True

        _logger.debug('Marking URL {0} status {1}.'.format(self._url, status))
        self._url_table.update(
            self._url,
            increment_try_count=increment_try_count,
            status=status
        )

        self._processed = True

    def set_value(self, **kwargs):
        '''Set values for the URL in table.'''
        self._url_table.update(self._url, **kwargs)

    def add_inline_url_infos(self, url_infos, encoding=None, link_type=None,
    post_data=None):
        '''Add inline links scraped from the document.

        Args:
            url_infos (iterable): A list of :class:`.url.URLInfo`
            encoding (str): The encoding of the document.
        '''
        inline_urls = tuple([info.url for info in url_infos])
        _logger.debug('Adding inline URLs {0}'.format(inline_urls))
        self._url_table.add(
            inline_urls,
            inline=True,
            level=self._url_record.level + 1,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            url_encoding=encoding,
            post_data=post_data,
        )

    def add_linked_url_infos(self, url_infos, encoding=None, link_type=None,
    post_data=None):
        '''Add linked links scraped from the document.

        Args:
            url_infos (iterable): A list of :class:`.url.URLInfo`
            encoding (str): The encoding of the document.
        '''
        linked_urls = tuple([info.url for info in url_infos])
        _logger.debug('Adding linked URLs {0}'.format(linked_urls))
        self._url_table.add(
            linked_urls,
            level=self._url_record.level + 1,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            link_type=link_type,
            url_encoding=encoding,
            post_data=post_data,
        )

    def add_url_item(self, url_info, request):
        # TODO: the request should be serialized into the url_table
        raise NotImplementedError()
