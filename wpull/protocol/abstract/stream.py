'''Abstract stream classes'''
import functools

import asyncio

import wpull.util


def close_stream_on_error(func):
    '''Decorator to close stream on error.'''
    @asyncio.coroutine
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with wpull.util.close_on_error(self.close):
            return (yield from func(self, *args, **kwargs))
    return wrapper
