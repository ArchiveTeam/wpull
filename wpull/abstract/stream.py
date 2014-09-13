'''Abstract stream classes'''
import functools

import trollius
from trollius import Return, From

import wpull.util


def close_stream_on_error(func):
    '''Decorator to close stream on error.'''
    @trollius.coroutine
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        with wpull.util.close_on_error(self.close):
            raise Return((yield From(func(self, *args, **kwargs))))
    return wrapper
