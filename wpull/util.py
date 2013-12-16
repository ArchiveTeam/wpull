import contextlib
import tornado.gen
import tornado.ioloop
import toro
import time


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
    return time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
