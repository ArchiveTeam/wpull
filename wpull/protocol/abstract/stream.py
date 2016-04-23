'''Abstract stream classes'''
import functools

import asyncio

from typing import Callable

import wpull.util


def close_stream_on_error(func):
    '''Decorator to close stream on error.'''
    @asyncio.coroutine
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with wpull.util.close_on_error(self.close):
            return (yield from func(self, *args, **kwargs))
    return wrapper


DataEventCallback = Callable[[bytes], None]


class DataEventDispatcher(object):
    def __init__(self):
        self._read_listeners = set()
        self._write_listeners = set()

    def add_read_listener(self, callback: DataEventCallback):
        self._read_listeners.add(callback)

    def remove_read_listener(self, callback: DataEventCallback):
        self._read_listeners.remove(callback)

    def add_write_listener(self, callback: DataEventCallback):
        self._write_listeners.add(callback)

    def remove_write_listener(self, callback: DataEventCallback):
        self._write_listeners.remove(callback)

    def notify_read(self, data: bytes):
        for callback in self._read_listeners:
            callback(data)

    def notify_write(self, data: bytes):
        for callback in self._write_listeners:
            callback(data)
