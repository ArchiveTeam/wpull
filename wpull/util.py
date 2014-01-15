# encoding=utf-8
import collections
import contextlib
import copy
import sys
import time
import tornado.gen
import tornado.ioloop
import toro


try:
    from collections import OrderedDict
except ImportError:
    from wpull.backport.collections import OrderedDict


class OrderedDefaultDict(OrderedDict):
    '''http://stackoverflow.com/a/6190500/1524507'''
    def __init__(self, default_factory=None, *args, **kwargs):
        if default_factory is not None and \
        not isinstance(default_factory, collections.Callable):
            raise TypeError('First argument must be callable')
        OrderedDict.__init__(self, *args, **kwargs)
        self.default_factory = default_factory

    def __getitem__(self, key):
        try:
            return OrderedDict.__getitem__(self, key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value

    def __reduce__(self):
        if self.default_factory is None:
            args = tuple()
        else:
            args = self.default_factory,
        return type(self), args, None, None, self.items()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return type(self)(self.default_factory, self)

    def __deepcopy__(self, memo):
        return type(self)(self.default_factory, copy.deepcopy(self.items()))

    def __repr__(self):
        return 'OrderedDefaultDict(%s, %s)' % (
            self.default_factory, collections.OrderedDict.__repr__(self))


@contextlib.contextmanager
def reset_file_offset(file):
    offset = file.tell()
    yield
    file.seek(offset)


def peek_file(file):
    with reset_file_offset(file):
        return file.read(4096)


def to_bytes(instance, encoding='utf-8'):
    if hasattr(instance, 'encode'):
        return instance.encode(encoding)
    elif isinstance(instance, list):
        return list([to_bytes(item, encoding) for item in instance])
    elif isinstance(instance, tuple):
        return tuple([to_bytes(item, encoding) for item in instance])
    return instance


def to_str(instance, encoding='utf-8'):
    if hasattr(instance, 'decode'):
        return instance.decode(encoding)
    elif isinstance(instance, list):
        return list([to_str(item, encoding) for item in instance])
    elif isinstance(instance, tuple):
        return tuple([to_str(item, encoding) for item in instance])
    return instance


@tornado.gen.coroutine
def sleep(seconds):
    assert seconds >= 0.0
    io_loop = tornado.ioloop.IOLoop.current()
    try:
        yield toro.AsyncResult().get(io_loop.time() + seconds)
    except toro.Timeout:
        pass


def datetime_str():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TimedOut(Exception):
    pass


@tornado.gen.coroutine
def wait_future(future, seconds=None):
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


def python_version():
    major, minor, patch = sys.version_info[0:3]
    return '{0}.{1}.{2}'.format(major, minor, patch)
