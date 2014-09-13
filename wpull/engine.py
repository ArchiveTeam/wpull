# encoding=utf-8
'''Item queue management and processing.'''
import abc
import contextlib
import gettext
import logging
import os

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.database.base import NotFound
from wpull.hook import HookableMixin, HookDisconnected
from wpull.item import Status, URLItem
from wpull.url import parse_url_or_log


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseEngine(object):
    '''Base engine producer-consumer.'''
    POISON_PILL = object()
    ITEM_PRIORITY = 1
    POISON_PRIORITY = 0

    def __init__(self):
        super().__init__()
        self.__concurrent = 1
        self._running = False
        self._item_queue = trollius.PriorityQueue()
        self._token_queue = trollius.JoinableQueue()
        self._item_get_semaphore = trollius.BoundedSemaphore(value=1)

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
        self._producer_task = trollius.async(self._run_producer_wrapper())
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

        if self._item_get_semaphore.locked():
            _logger.warning(__(
                gettext.ngettext(
                    'Discarding {num} unprocessed item.',
                    'Discarding {num} unprocessed items.',
                    self._token_queue.qsize()
                ),
                num=self._token_queue.qsize()
            ))
            self._item_get_semaphore.release()

        yield From(self._producer_task)

    @trollius.coroutine
    def _run_producer_wrapper(self):
        '''Run the producer, if exception, stop engine.'''
        try:
            yield From(self._run_producer())
        except Exception as error:
            if not isinstance(error, StopIteration):
                # Stop the workers so the producer exception will be handled
                _logger.error('Producer died.')
                self._stop()
            raise

    @trollius.coroutine
    def _run_producer(self):
        '''Run the producer.

        Coroutine.
        '''
        while self._running:
            _logger.debug('Get item from source')
            item = yield From(self._get_item())

            # FIXME: accessing protected unfinished_tasks
            if item is None and self._token_queue._unfinished_tasks == 0:
                _logger.debug('Producer stopping.')
                self._stop()
            elif item is None:
                _logger.debug(
                    __('Producer waiting for {0} workers to finish up.',
                        len(self._worker_tasks)))
                yield From(self._token_queue.join())
            else:
                yield From(self._item_get_semaphore.acquire())
                self._token_queue.put_nowait(None)
                yield From(self._item_queue.put((self.ITEM_PRIORITY, item)))

    @trollius.coroutine
    def _run_worker(self):
        '''Run a single consumer.

        Coroutine.
        '''
        _logger.debug('Worker start.')

        while True:
            priority, item = yield From(self._item_queue.get())

            if item == self.POISON_PILL:
                _logger.debug('Worker quitting.')
                return

            else:
                _logger.debug(__('Processing item {0}.', item))
                self._item_get_semaphore.release()
                self._token_queue.get_nowait()
                yield From(self._process_item(item))
                self._token_queue.task_done()

                if os.environ.get('OBJGRAPH_DEBUG'):
                    import gc
                    import objgraph
                    gc.collect()
                    objgraph.show_most_common_types(25)
                if os.environ.get('FILE_LEAK_DEBUG'):
                    import subprocess
                    output = subprocess.check_output(
                        ['lsof', '-p', str(os.getpid()), '-n'])
                    for line in output.decode('ascii', 'replace').split('\n'):
                        if 'REG' in line and \
                                (os.getcwd() in line or '/tmp/' in line):
                            print('FILELEAK', line)

    def _set_concurrent(self, new_num):
        '''Set concurrency level.'''
        if self._running:
            assert new_num >= 0, \
                'No negative concurrency pls. Got {}.'.format(new_num)
            change = new_num - self.__concurrent

            if change < 0:
                for dummy in range(abs(change)):
                    _logger.debug('Put poison pill for less workers.')
                    self._item_queue.put_nowait(
                        (self.POISON_PRIORITY, self.POISON_PILL))
            elif change > 0:
                _logger.debug('Put 1 poison pill to trigger more workers.')
                self._item_queue.put_nowait(
                    (self.POISON_PRIORITY, self.POISON_PILL))

        self.__concurrent = new_num

    def _stop(self):
        '''Gracefully stop.'''
        if self._running:
            self._running = False

            for dummy in range(len(self._worker_tasks)):
                _logger.debug('Put poison pill.')
                self._item_queue.put_nowait(
                    (self.POISON_PRIORITY, self.POISON_PILL))

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
                 concurrent=1, ignore_exceptions=False):
        super().__init__()

        self._url_table = url_table
        self._processor = processor
        self._statistics = statistics
        self._ignore_exceptions = ignore_exceptions
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
        with self._maybe_ignore_exceptions():
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
            url_record = self._url_table.check_out(Status.todo)
        except NotFound:
            url_record = None

        if not url_record:
            try:
                _logger.debug('Get next URL error.')
                url_record = self._url_table.check_out(Status.error)
            except NotFound:
                url_record = None

        _logger.debug(__('Return record {0}.', url_record))

        return url_record

    @trollius.coroutine
    def _process_item(self, url_record):
        '''Process given item.'''

        with self._maybe_ignore_exceptions():
            yield From(self._process_url_item(url_record))

    @trollius.coroutine
    def _process_url_item(self, url_record):
        '''Process an item.

        Args:
            url_item (:class:`.database.URLRecord`): The item to process.

        This function calls :meth:`.processor.BaseProcessor.process`.
        '''
        assert url_record

        url_info = parse_url_or_log(url_record.url)

        if not url_info:
            url_item = URLItem(self._url_table, None, url_record)
            url_item.skip()
            return

        url_item = URLItem(self._url_table, url_info, url_record)

        _logger.debug(__('Begin session for {0} {1}.',
                         url_record, url_item.url_info))

        yield From(self._processor.process(url_item))

        assert url_item.is_processed

        self._statistics.mark_done(url_info)

        if self._statistics.is_quota_exceeded:
            _logger.debug('Stopping due to quota.')
            self.stop()

        _logger.debug(__('End session for {0} {1}.',
                         url_item.url_record, url_item.url_info))

    def stop(self):
        '''Stop the engine.'''
        _logger.debug(__('Stopping'))
        self._stop()

    @contextlib.contextmanager
    def _maybe_ignore_exceptions(self):
        if self._ignore_exceptions:
            try:
                yield
            except Exception as error:
                if not isinstance(error, StopIteration):
                    _logger.exception('Ignored exception. Program unstable!')
                else:
                    raise
        else:
            yield
