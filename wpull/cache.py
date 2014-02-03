'''Caching.'''
import collections
import heapq
import sys
import time


if 'sphinx' not in sys.modules:
    try:
        from functools import total_ordering
    except ImportError:
        from wpull.backport.functools import total_ordering
else:
    total_ordering = lambda obj: obj


class Cache(collections.MutableMapping):
    '''Object cache.

    Args:
        max_items: The maximum number of items to keep
        time_to_live: The time in seconds of how long to keep the item
    '''
    def __init__(self, max_items=None, time_to_live=None):
        self._data = {}
        self._heap = []
        self._max_items = max_items
        self._time_to_live = time_to_live

    def expire(self):
        '''Remove old items.'''
        now_time = time.time()
        while True:
            if not self._heap:
                break

            if self._heap[0].expire_time < now_time:
                self.pop_top()
            else:
                break

        if self._max_items is not None:
            while len(self._heap) > self._max_items:
                self.pop_top()

    def pop_top(self):
        '''Delete and return the oldest item.'''
        item = heapq.heappop(self._heap)
        del self._data[item.key]
        return item

    def __iter__(self):
        return iter(self._data.keys())

    def __getitem__(self, key):
        self.expire()

        self._data[key].access_time = time.time()

        return self._data[key].value

    def __setitem__(self, key, value):
        self.expire()

        if key not in self._data:
            item = CacheItem(key, value, self._time_to_live)
            heapq.heappush(self._heap, item)
            self._data[key] = item
        else:
            self._data[key].value = value

    def __delitem__(self, key):
        item = self._data.pop(key)
        self._heap.remove(item)
        heapq.heapify(self._heap)

    def __len__(self):
        return len(self._data)


@total_ordering
class CacheItem(object):
    '''Info about an item in the cache.

    Args:
        key: The key
        value: The value
        time_to_live: The time in seconds of how long to keep the item
        access_time: The timestamp of the last use of the item
    '''
    def __init__(self, key, value, time_to_live=None, access_time=None):
        self.key = key
        self.value = value

        if time_to_live is None:
            self.time_to_live = float('+inf')
        else:
            self.time_to_live = time_to_live

        self.access_time = access_time or time.time()

    @property
    def expire_time(self):
        return self.access_time + self.time_to_live

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __eq__(self, other):
        return self.expire_time == other.expire_time
