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
    '''Base engine producer-consumer.'''
    POISON_PILL = object()

    def __init__(self):
        super().__init__()
        self.__concurrent = 1
        self._running = False
        self._item_queue = trollius.JoinableQueue(maxsize=1)
        self._poison_queue = trollius.Queue()

        self._producer_task = None
        self._worker_tasks = set()

    @property
    def _concurrent(self):
        '''Get concurrency value.'''
        return self.__concurrent

    @trollius.coroutine
    def _run_workers(self):
        '''Run the consumers.

        Coroutine.
        '''
        self._running = True
        self._producer_task = trollius.async(self._run_producer())
        worker_tasks = self._worker_tasks

        while self._running:
            while len(worker_tasks) < self.__concurrent:
                worker_task = trollius.async(self._run_worker())
                worker_tasks.add(worker_task)

            wait_coroutine = trollius.wait(
                worker_tasks, return_when=trollius.FIRST_COMPLETED)
            done_tasks = (yield From(wait_coroutine))[0]

            for task in done_tasks:
                task.result()
                worker_tasks.remove(task)

        _logger.debug('Exited workers loop.')

        if worker_tasks:
            _logger.debug('Waiting for workers to stop.')
            yield From(trollius.wait(worker_tasks))

        _logger.debug('Waiting for producer to stop.')
        yield From(self._producer_task)

    @trollius.coroutine
    def _run_producer(self):
        '''Run the producer.

        Coroutine.
        '''
        while self._running:
            item = yield From(self._get_item())

            # FIXME: unfinished_tasks
            if item is None and self._item_queue._unfinished_tasks == 0:
                _logger.debug('Producer stopping.')
                self._stop()
            elif item is None:
                _logger.debug('Producer waiting for a workers to finish up.')
                yield From(self._item_queue.join())
            else:
                yield From(self._item_queue.put(item))

    @trollius.coroutine
    def _run_worker(self):
        '''Run a single consumer.

        Coroutine.
        '''
        _logger.debug('Worker start.')

        while True:
            tasks = (self._item_queue.get(), self._poison_queue.get())
            done_tasks, pending_tasks = yield From(
                trollius.wait(tasks, return_when=trollius.FIRST_COMPLETED))

            for task in pending_tasks:
                task.cancel()

            items = tuple(task.result() for task in done_tasks)

            if len(items) == 2 and items[0] == self.POISON_PILL:
                # Always do poison pill last.
                items = reversed(items)

            for item in items:
                if item == self.POISON_PILL:
                    _logger.debug('Worker quitting.')
                    return

                else:
                    _logger.debug(__('Processing item {0}.', item))
                    yield From(self._process_item(item))
                    self._item_queue.task_done()

    def _set_concurrent(self, new_num):
        '''Set concurrency level.'''
        if self._running:
            assert new_num >= 0
            change = new_num - self.__concurrent

            if change < 0:
                for dummy in range(abs(change)):
                    _logger.debug('Put poison pill for less workers.')
                    self._poison_queue.put_nowait(self.POISON_PILL)
            elif change > 0:
                _logger.debug('Put 1 poison pill to trigger more workers.')
                self._poison_queue.put_nowait(self.POISON_PILL)

        self.__concurrent = new_num

    def _stop(self):
        '''Gracefully stop.'''
        if self._running:
            self._running = False

            for dummy in range(len(self._worker_tasks)):
                _logger.debug('Put poison pill.')
                self._poison_queue.put_nowait(self.POISON_PILL)

    @abc.abstractmethod
    @trollius.coroutine
    def _get_item(self):
        '''Get an item.

        Coroutine.
        '''
        pass

    @abc.abstractmethod
    @trollius.coroutine
    def _process_item(self, item):
        '''Process an item.

        Coroutine.
        '''


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
        self._num_worker_busy = 0

        self._set_concurrent(concurrent)
        self.register_hook('engine_run')

    @property
    def concurrent(self):
        '''The concurrency value.'''
        return self._concurrent

    def set_concurrent(self, value):
        '''Set concurrency value.'''
        self._set_concurrent(value)

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
