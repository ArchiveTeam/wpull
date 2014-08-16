# encoding=utf-8
'''Item queue management and processing.'''
import gettext
import logging

import trollius
from trollius import From, Return

from wpull.backport.logging import BraceMessage as __
from wpull.database import NotFound
from wpull.hook import HookableMixin, HookDisconnected
from wpull.item import Status, URLItem
from wpull.url import URLInfo
import abc


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseEngine(object):
    def __init__(self):
        super().__init__()
        self._concurrent = 1
        self._running = False
        self._item_queue = trollius.JoinableQueue()

    @trollius.coroutine
    def _run_workers(self):
        self._running = True
        worker_tasks = set()

        while self._running:
            while len(worker_tasks) < self._concurrent:
                worker_task = trollius.async(self._run_worker())
                worker_tasks.add(worker_task)

            item = yield From(self._get_item())

            # FIXME: unfinished_tasks
            if item is None and self._item_queue._unfinished_tasks == 0:
                break
            elif item is not None:
                self._item_queue.put_nowait(item)

            wait_coroutine = trollius.wait(
                worker_tasks, return_when=trollius.FIRST_COMPLETED)
            done_tasks = (yield From(wait_coroutine))[0]

            for task in done_tasks:
                task.result()
                worker_tasks.remove(task)

        yield From(self._item_queue.join())

        if worker_tasks:
            yield From(trollius.wait(worker_tasks))

    @trollius.coroutine
    def _run_worker(self):
        try:
            item = yield From(trollius.wait_for(self._item_queue.get(), 0.2))
        except (trollius.QueueEmpty, trollius.TimeoutError):
            return

        _logger.debug(__('Processing item {0}.', item))
        yield From(self._process_item(item))

        self._item_queue.task_done()

    def _stop(self):
        self._running = False

    @abc.abstractmethod
    @trollius.coroutine
    def _get_item(self):
        pass

    @abc.abstractmethod
    @trollius.coroutine
    def _process_item(self, item):
        pass


class Engine(BaseEngine, HookableMixin):
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
        self._concurrent = concurrent
        self._num_worker_busy = 0

        self.register_hook('engine_run')

    @property
    def concurrent(self):
        '''The concurrency value.'''
        return self._concurrent

    def set_concurrent(self, value):
        self._concurrent = value

    @trollius.coroutine
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
        yield From(self._run_workers())

    def _release_in_progress(self):
        '''Release any items in progress.'''
        _logger.debug('Release in-progress.')
        self._url_table.release()

    @trollius.coroutine
    def _get_item(self):
        return self._get_next_url_record()

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

    @trollius.coroutine
    def _process_item(self, url_record):
        '''Process given item.'''
        assert url_record

        url_encoding = url_record.url_encoding or 'utf8'
        url_info = URLInfo.parse(url_record.url, encoding=url_encoding)
        url_item = URLItem(self._url_table, url_info, url_record)

        yield From(self._process_url_item(url_item))

        assert url_item.is_processed

        self._statistics.mark_done(url_info)

        if self._statistics.is_quota_exceeded:
            _logger.debug('Stopping due to quota.')
            self.stop()

    @trollius.coroutine
    def _process_url_item(self, url_item):
        '''Process an item.

        Args:
            url_item (:class:`.item.URLItem`): The item to process.

        This function calls :meth:`.processor.BaseProcessor.process`.
        '''
        _logger.debug(__('Begin session for {0} {1}.',
                         url_item.url_record, url_item.url_info))

        yield From(self._processor.process(url_item))

        _logger.debug(__('End session for {0} {1}.',
                         url_item.url_record, url_item.url_info))

    def stop(self):
        '''Stop the engine.'''
        _logger.debug(__('Stopping'))
        self._stop()
