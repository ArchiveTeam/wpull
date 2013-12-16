import collections
import contextlib
import copy
import time
import tornado.gen
import tornado.ioloop
import toro


class OrderedDefaultDict(collections.OrderedDict):
    '''http://stackoverflow.com/a/6190500/1524507'''
    def __init__(self, default_factory=None, *args, **kwargs):
        if default_factory is not None and \
        not isinstance(default_factory, collections.Callable):
            raise TypeError('First argument must be callable')
        collections.OrderedDict.__init__(self, *args, **kwargs)
        self.default_factory = default_factory

    def __getitem__(self, key):
        try:
            return collections.OrderedDict.__getitem__(self, key)
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
    io_loop = tornado.ioloop.IOLoop.instance()
    try:
        yield toro.AsyncResult().get(io_loop.time() + seconds)
    except toro.Timeout:
        pass


def datetime_str():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
