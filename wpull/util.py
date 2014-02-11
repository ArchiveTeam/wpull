# encoding=utf-8
'''Miscellaneous functions.'''
import calendar
import chardet
import codecs
import collections
import contextlib
import copy
import datetime
import itertools
import re
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
    '''An ordered default dict.

    http://stackoverflow.com/a/6190500/1524507
    '''
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


class ASCIIStreamWriter(codecs.StreamWriter):
    '''A Stream Writer that encodes everything to ASCII.

    By default, the replacement character is a Python backslash sequence.
    '''
    DEFAULT_ERROR = 'backslashreplace'

    def __init__(self, stream, errors=DEFAULT_ERROR):
        codecs.StreamWriter.__init__(self, stream, errors)

    def encode(self, instance, errors=DEFAULT_ERROR):
        return instance.encode('ascii', errors)

    def decode(self, instance, errors=DEFAULT_ERROR):
        return instance.encode('ascii', errors)

    def write(self, instance):
        if hasattr(instance, 'encode'):
            instance = instance.encode('ascii', self.errors)

        if hasattr(instance, 'decode'):
            instance = instance.decode('ascii', self.errors)

        self.stream.write(instance)

    def writelines(self, list_instance):
        for item in list_instance:
            self.write(item)


@contextlib.contextmanager
def reset_file_offset(file):
    '''Reset the file offset back to original position.'''
    offset = file.tell()
    yield
    file.seek(offset)


def peek_file(file):
    with reset_file_offset(file):
        return file.read(4096)


def to_bytes(instance, encoding='utf-8'):
    '''Convert an instance recursively to bytes.'''
    if isinstance(instance, bytes):
        return instance
    elif hasattr(instance, 'encode'):
        return instance.encode(encoding)
    elif isinstance(instance, list):
        return list([to_bytes(item, encoding) for item in instance])
    elif isinstance(instance, tuple):
        return tuple([to_bytes(item, encoding) for item in instance])
    elif isinstance(instance, dict):
        return dict(
            [(to_bytes(key, encoding), to_bytes(value, encoding))
                for key, value in instance.items()])
    return instance


def to_str(instance, encoding='utf-8'):
    '''Convert an instance recursively to string.'''
    if isinstance(instance, str):
        return instance
    elif hasattr(instance, 'decode'):
        return instance.decode(encoding)
    elif isinstance(instance, list):
        return list([to_str(item, encoding) for item in instance])
    elif isinstance(instance, tuple):
        return tuple([to_str(item, encoding) for item in instance])
    elif isinstance(instance, dict):
        return dict(
            [(to_str(key, encoding), to_str(value, encoding))
                for key, value in instance.items()])
    return instance


@tornado.gen.coroutine
def sleep(seconds):
    '''Sleep asynchronously.'''
    assert seconds >= 0.0
    io_loop = tornado.ioloop.IOLoop.current()
    try:
        yield toro.AsyncResult().get(io_loop.time() + seconds)
    except toro.Timeout:
        pass


def datetime_str():
    '''Return the current time in simple ISO8601 notation.'''
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_iso8601_str(string):
    '''Parse a fixed ISO8601 datetime string.

    .. Note:: This function only parses dates in the format
       ``%Y-%m-%dT%H:%M:%SZ``. You must use a library like ``dateutils``
       to properly parse dates and times.

    Returns:
        float: A UNIX timestamp.
    '''
    datetime_obj = datetime.datetime.strptime(string, "%Y-%m-%dT%H:%M:%SZ")
    return int(calendar.timegm(datetime_obj.utctimetuple()))


class TimedOut(Exception):
    '''Coroutine timed out before it could finish.'''
    pass


@tornado.gen.coroutine
def wait_future(future, seconds=None):
    '''Wait for a future to complete with timeouts.

    Args:
        future: a Future
        seconds: The time in seconds before the coroutine is timed out

    Raises:
        :class:`TimedOut` when the coroutine does not finish in time
    '''
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
    '''Return the Python version as a string.'''
    major, minor, patch = sys.version_info[0:3]
    return '{0}.{1}.{2}'.format(major, minor, patch)


def filter_pem(data):
    '''Processes the bytes for PEM certificates.

    Returns:
        ``set`` containing each certificate
    '''
    assert isinstance(data, bytes)
    certs = set()
    new_list = []
    in_pem_block = False

    for line in re.split(br'[\r\n]+', data):
        if line == b'-----BEGIN CERTIFICATE-----':
            assert not in_pem_block
            in_pem_block = True
            new_list.append(line)
        elif line == b'-----END CERTIFICATE-----':
            assert in_pem_block
            in_pem_block = False
            new_list.append(line)

            # Add trailing new line
            new_list.append(b'')

            certs.add(b'\n'.join(new_list))

            new_list = []
        elif in_pem_block:
            new_list.append(line)

    return certs


def normalize_codec_name(name):
    '''Return the Python name of the encoder/decoder'''
    if name:
        return codecs.lookup(name).name


def detect_encoding(data, encoding=None, fallback=('utf8', 'latin1')):
    '''Detect the character encoding of the data.

    Returns:
        The name of the codec

    Raises:
        :class:`ValueError` if the codec could not be detected.
    '''
    encoding = normalize_codec_name(encoding)
    info = chardet.detect(data)
    detected_encoding = normalize_codec_name(info['encoding'])
    candidates = itertools.chain((encoding, detected_encoding), fallback)

    for candidate in candidates:
        if not candidate:
            continue

        if try_decoding(data, candidate):
            return candidate

    raise ValueError('Unable to detect encoding.')


def try_decoding(data, encoding):
    '''Return whether the Python codec could decode the data.'''
    try:
        data.decode(encoding, 'strict')
    except UnicodeError:
        return False
    else:
        return True


def format_size(num, format_str='{num:.1f} {unit}'):
    '''Format the file size into a human readable text.

    http://stackoverflow.com/a/1094933/1524507
    '''
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if num < 1024 and num > -1024:
            return format_str.format(num=num, unit=unit)

        num /= 1024.0

    return format_str.format(num, unit='TiB')
