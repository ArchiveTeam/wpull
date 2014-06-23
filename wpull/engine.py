# encoding=utf-8
'''Item queue management and processing.'''
import gettext
import logging

import tornado.gen
import toro

from wpull.async import AdjustableSemaphore
import wpull.async
from wpull.backport.logging import BraceMessage as __
from wpull.database import NotFound
from wpull.hook import HookableMixin, HookDisconnected
from wpull.item import Status, URLItem
from wpull.url import URLInfo


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Engine(HookableMixin):
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

    def __init__(self, url_table, processor, statistics,
                 concurrent=1):
        super().__init__()

        self._url_table = url_table
        self._processor = processor
        self._statistics = statistics
        self._worker_semaphore = AdjustableSemaphore(concurrent)
        self._done_event = toro.Event()
        self._num_worker_busy = 0
        self._stopping = False
        self._worker_error = None

        self.register_hook('engine_run')

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
        try:
            self.call_hook('engine_run')
        except HookDisconnected:
            pass

        self._release_in_progress()
        self._run_workers()

        yield self._done_event.wait()

        self._processor.close()
        self._url_table.close()

        if self._worker_error:
            raise self._worker_error from self._worker_error

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

        _logger.debug(__('Return record {0}.', url_record))

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
            _logger.debug('Worker died from error.')
            self.stop(force=True)
            self._worker_error = error

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
        _logger.debug(__('Begin session for {0} {1}.',
                         url_item.url_record, url_item.url_info))

        yield self._processor.process(url_item)

        _logger.debug(__('End session for {0} {1}.',
                         url_item.url_record, url_item.url_info))

    def stop(self, force=False):
        '''Stop the engine.

        Args:
            force (bool): If ``True``, don't wait for Sessions to finish and
            stop the Engine immediately. If ``False``, the Engine will wait
            for all workers to finish.
        '''
        _logger.debug(__('Stopping. force={0}', force))

        self._stopping = True

        if force:
            self._done_event.set()
