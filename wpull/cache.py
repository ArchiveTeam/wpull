'''Caching.'''
import abc
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


class BaseCache(collections.Mapping):
    @abc.abstractmethod
    def __setitem__(self, key, value):
        pass

    @abc.abstractmethod
    def clear(self):
        '''Remove all items in cache.'''


class FIFOCache(BaseCache):
    '''First in first out object cache.

    Args:
        max_items (int): The maximum number of items to keep.
        time_to_live (float): Discard items after `time_to_live` seconds.

    Reusing a key to update a value will not affect the expire time of the
    item.
    '''
    def __init__(self, max_items=None, time_to_live=None):
        self._map = {}
        self._deque = collections.deque()
        self._max_items = max_items
        self._time_to_live = time_to_live

    def __getitem__(self, key):
        self.trim()

        return self._map[key].value

    def __iter__(self):
        return iter(self._map.keys())

    def __len__(self):
        return len(self._map)

    def __setitem__(self, key, value):
        if key in self._map:
            self._map[key].value = value
        else:
            item = CacheItem(key, value, self._time_to_live)
            self._map[key] = item
            self._deque.append(item)

            self.trim()

    def clear(self):
        self._map = {}
        self._deque = collections.deque()

    def trim(self):
        '''Remove items that are expired or exceed the max size.'''
        now_time = time.time()

        while self._deque and self._deque[0].expire_time < now_time:
            item = self._deque.popleft()
            del self._map[item.key]

        if self._max_items:
            while self._deque and len(self._deque) > self._max_items:
                item = self._deque.popleft()
                del self._map[item.key]


class Cache(collections.MutableMapping):
    # TODO: rewrite this into LRUCache
    '''Object cache.

    .. warning:: Do not use this class. The time to live feature is broken
        in some ways.

        This class will be made an alias to a LRUCache in the future.

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
        '''When the item expires.'''
        return self.access_time + self.time_to_live

    def __lt__(self, other):
        return self.expire_time < other.expire_time

    def __eq__(self, other):
        return self.expire_time == other.expire_time

    def __repr__(self):
        return (
            '<CacheItem({key}, {value}, '
            'time_to_live={ttl}, access_time={access_time})'
            ' at 0x{id:x}>').format(
                key=self.key, value=self.value,
                ttl=self.time_to_live,
                access_time=self.access_time, id=id(self)
            )
