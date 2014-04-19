# encoding=utf-8
'''Asynchronous functions.'''
import datetime

import tornado.gen
import toro


class AdjustableSemaphore(toro.Semaphore):
    '''An adjustable semaphore.'''
    def __init__(self, value=1, io_loop=None):
        self._max_value = value
        self._num_acquired = 0
        super().__init__(value=value, io_loop=None)

    @property
    def max(self):
        '''The upper bound of the value.'''
        return self._max_value

    def set_max(self, value):
        '''Set the upper bound the value.'''
        if value < 0:
            raise ValueError('Maximum must be 0 or positive.')

        self._max_value = value

        while self.q.qsize() + self._num_acquired < self._max_value:
            self.q.put_nowait(None)

    def acquire(self, deadline=None):
        def increment_cb(future):
            if not future.cancelled() and not future.exception():
                self._num_acquired += 1

        future = super().acquire(deadline=deadline)

        future.add_done_callback(increment_cb)

        return future

    def release(self):
        # Copied and modified from toro
        """Increment :attr:`counter` and wake waiters based on :attr:`max`.
        """
        self._num_acquired -= 1

        if self._num_acquired < 0:
            raise ValueError('Semaphore released too many times.')

        while self.q.qsize() + self._num_acquired < self._max_value:
            self.q.put_nowait(None)

        if not self.locked():
            # No one was waiting on acquire(), so self.q.qsize() is positive
            self._unlocked.set()


class TimedOut(Exception):
    '''Coroutine timed out before it could finish.'''
    pass


@tornado.gen.coroutine
def wait_future(future, seconds=None):
    '''Wait for a future to complete with timeouts.

    Args:
        future: a Future
        seconds: The time in seconds before the coroutine is timed out

    Raises:
        :class:`TimedOut` when the coroutine does not finish in time
    '''
    if seconds is None:
        result = yield future
        raise tornado.gen.Return(result)

    assert seconds >= 0.0
    io_loop = tornado.ioloop.IOLoop.current()
    async_result = toro.AsyncResult()
    io_loop.add_future(future, async_result.set)
    try:
        future = yield async_result.get(io_loop.time() + seconds)
        result = future.result()
    except toro.Timeout as error:
        raise TimedOut() from error
    raise tornado.gen.Return(result)


@tornado.gen.coroutine
def sleep(seconds):
    '''Sleep asynchronously.'''
    assert seconds >= 0.0
    yield tornado.gen.Task(
        tornado.ioloop.IOLoop.current().add_timeout,
        datetime.timedelta(seconds=seconds)
    )
