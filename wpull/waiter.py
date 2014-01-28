# encoding=utf-8
'''Delays between requests.'''
import abc
import random


class Waiter(object, metaclass=abc.ABCMeta):
    '''Base class for Waiters.

    Waiters are counters that indicate the delay between requests.
    '''
    @abc.abstractmethod
    def get(self):
        '''Return the time in seconds.'''
        pass

    @abc.abstractmethod
    def increment(self):
        '''Increment the delay possibly due to an error.'''
        pass

    @abc.abstractmethod
    def reset(self):
        '''Reset the delay back to normal setting.'''
        pass


class LinearWaiter(Waiter):
    '''A linear back-off waiter.

    Args:
        wait: The normal delay time
        random_wait: If True, randomly perturb the delay time within a factor
            of 0.5 and 1.5
        max_wait: The maximum delay time

    This waiter will increment by values of 1 second.
    '''
    def __init__(self, wait=0.0, random_wait=False, max_wait=10.0):
        self._wait = wait
        self._current = wait
        self._random = random_wait
        self._max_wait = max_wait

    def get(self):
        if self._random:
            return self._current * random.uniform(0.5, 1.5)
        else:
            return self._current

    def increment(self):
        self._current = min(self._max_wait, self._current + 1)

    def reset(self):
        self._current = self._wait
