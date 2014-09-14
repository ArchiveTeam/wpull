'''Caching.'''
import abc
import collections
import sys
import time

from wpull.collections import LinkedList


if 'sphinx' not in sys.modules:
    try:
        from functools import total_ordering
    except ImportError:
        from wpull.backport.functools import total_ordering
else:
    total_ordering = lambda obj: obj


class BaseCache(collections.Mapping, object):
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
        super().__init__()
        self._map = {}
        self._seq = collections.deque()
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
            self._seq.append(item)

            self.trim()

    def clear(self):
        self._map = {}
        self._seq = collections.deque()

    def trim(self):
        '''Remove items that are expired or exceed the max size.'''
        now_time = time.time()

        while self._seq and self._seq[0].expire_time < now_time:
            item = self._seq.popleft()
            del self._map[item.key]

        if self._max_items:
            while self._seq and len(self._seq) > self._max_items:
                item = self._seq.popleft()
                del self._map[item.key]


class LRUCache(FIFOCache):
    '''Least recently used object cache.

    Args:
        max_items: The maximum number of items to keep
        time_to_live: The time in seconds of how long to keep the item
    '''
    def __init__(self, max_items=None, time_to_live=None):
        super().__init__(max_items=max_items, time_to_live=time_to_live)
        self._seq = LinkedList()

    def __getitem__(self, key):
        self.trim()
        self.touch(key)

        return self._map[key].value

    def __setitem__(self, key, value):
        if key in self._map:
            self._map[key].value = value
            self.touch(key)

        else:
            item = CacheItem(key, value, self._time_to_live)
            self._map[key] = item
            self._seq.append(item)

            self.trim()

    def touch(self, key):
        self._map[key].access_time = time.time()
        self._seq.remove(self._map[key])
        self._seq.append(self._map[key])


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
        if self.expire_time < other.expire_time:
            return True
        else:
            return id(self.key) < id(other.key)

    def __eq__(self, other):
        return self.expire_time == other.expire_time and self.key == other.key

    def __repr__(self):
        return (
            '<CacheItem({key}, {value}, '
            'time_to_live={ttl}, access_time={access_time})'
            ' at 0x{id:x}>').format(
                key=self.key, value=self.value,
                ttl=self.time_to_live,
                access_time=self.access_time, id=id(self)
        )

    def __hash__(self):
        return hash(self.key)


Cache = LRUCache
