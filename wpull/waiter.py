# encoding=utf-8
import abc
import random


class Waiter(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get(self):
        pass

    @abc.abstractmethod
    def increment(self):
        pass

    @abc.abstractmethod
    def reset(self):
        pass


class LinearWaiter(Waiter):
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
