# encoding=utf-8
'''Miscellaneous functions.'''
from bs4.dammit import UnicodeDammit, EncodingDetector
import calendar
import codecs
import collections
import contextlib
import copy
import datetime
import itertools
import os.path
import re
import sys
import time
import tornado.gen
import tornado.ioloop
import tornado.util
import toro
import zipfile
import zlib


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


class GzipDecompressor(tornado.util.GzipDecompressor):
    '''gzip decompressor with gzip header detection.

    This class checks if the stream starts with the 2 byte gzip magic number.
    If it is not present, it returns the bytes unchanged.
    '''
    def __init__(self):
        super().__init__()
        self.checked = False
        self.is_ok = None

    def decompress(self, value):
        if self.checked:
            if self.is_ok:
                return super().decompress(value)
            else:
                return value
        else:
            self.checked = True
            if value[:2] == b'\x1f\x8b':
                self.is_ok = True
                return super().decompress(value)
            else:
                self.is_ok = False
                return value

    def flush(self):
        if self.is_ok:
            return super().flush()
        else:
            return b''


class DeflateDecompressor(tornado.util.GzipDecompressor):
    '''zlib decompressor with raw deflate detection.

    This class doesn't do any special. It only tries regular zlib and then
    tries raw deflate on the first decompress.
    '''
    def __init__(self):
        super().__init__()
        self.decompressobj = None

    def decompress(self, value):
        if not self.decompressobj:
            try:
                self.decompressobj = zlib.decompressobj()
                return self.decompressobj.decompress(value)
            except zlib.error:
                self.decompressobj = zlib.decompressobj(-zlib.MAX_WBITS)
                return self.decompressobj.decompress(value)

        return self.decompressobj.decompress(value)


@contextlib.contextmanager
def reset_file_offset(file):
    '''Reset the file offset back to original position.'''
    offset = file.tell()
    yield
    file.seek(offset)


def peek_file(file, length=4096):
    '''Peek the file by calling ``read`` on it.'''
    with reset_file_offset(file):
        return file.read(length)


def to_bytes(instance, encoding='utf-8', error='strict'):
    '''Convert an instance recursively to bytes.'''
    if isinstance(instance, bytes):
        return instance
    elif hasattr(instance, 'encode'):
        return instance.encode(encoding, error)
    elif isinstance(instance, list):
        return list([to_bytes(item, encoding, error) for item in instance])
    elif isinstance(instance, tuple):
        return tuple([to_bytes(item, encoding, error) for item in instance])
    elif isinstance(instance, dict):
        return dict(
            [(to_bytes(key, encoding, error), to_bytes(value, encoding, error))
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
    yield tornado.gen.Task(
        tornado.ioloop.IOLoop.current().add_timeout,
        datetime.timedelta(seconds=seconds)
    )


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
    '''Return the Python name of the encoder/decoder

    Returns:
        str, None
    '''
    name = UnicodeDammit.CHARSET_ALIASES.get(name.lower(), name)

    try:
        return codecs.lookup(name).name
    except LookupError:
        pass


def detect_encoding(data, encoding=None, fallback='latin1', is_html=False):
    '''Detect the character encoding of the data.

    Returns:
        str: The name of the codec

    Raises:
        ValueError: The codec could not be detected. This error can only
        occur if fallback is not a "lossless" codec.
    '''
    if encoding:
        encoding = normalize_codec_name(encoding)

    bs4_detector = EncodingDetector(
        data,
        override_encodings=(encoding,) if encoding else (),
        is_html=is_html
    )
    candidates = itertools.chain(bs4_detector.encodings, (fallback,))

    for candidate in candidates:
        if not candidate:
            continue

        candidate = normalize_codec_name(candidate)

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


def truncate_file(path):
    '''Truncate the file.'''
    with open(path, 'wb'):
        pass


def gzip_uncompress(data, truncated=False):
    '''Uncompress gzip data.

    Args:
        data (bytes): The gzip data.
        truncated (bool): If True, the decompressor is not flushed.

    Returns:
        bytes: The inflated data.

    Raises:
        zlib.error
    '''
    decompressor = tornado.util.GzipDecompressor()
    inflated_data = decompressor.decompress(data)

    if not truncated:
        inflated_data += decompressor.flush()

    return inflated_data


ALL_BYTES = bytes(bytearray(range(256)))
CONTROL_BYTES = bytes(bytearray(
    itertools.chain(range(0, 32), range(127, 256))
))


def printable_bytes(data):
    '''Remove any bytes that is not printable ASCII.'''
    return data.translate(ALL_BYTES, CONTROL_BYTES)


def coerce_str_to_ascii(string):
    '''Force the contents of the string to be ASCII.

    Anything not ASCII will be replaced with with a replacement character.
    '''
    return string.encode('ascii', 'replace').decode('ascii')


def get_package_data(filename, mode='rb'):
    '''Return the contents of a real file or a zip file.'''
    if os.path.exists(filename):
        with open(filename, mode=mode) as in_file:
            return in_file.read()
    else:
        parts = os.path.normpath(filename).split(os.sep)

        for part, index in zip(parts, range(len(parts))):
            if part.endswith('.zip'):
                zip_path = os.sep.join(parts[:index + 1])
                member_path = os.sep.join(parts[index + 1:])

        with zipfile.ZipFile(zip_path) as zip_file:
            return zip_file.read(member_path)


def get_package_filename(filename, package_dir=None):
    '''Return the filename of the data file.'''
    if getattr(sys, 'frozen', False):
        package_dir = os.path.dirname(sys.executable)
    elif not package_dir:
        package_dir = os.path.dirname(__file__)

    return os.path.join(package_dir, filename)


class AdjustableSemaphore(toro.Semaphore):
    '''An adjustable semaphore.'''
    def __init__(self, value=1, io_loop=None):
        self._max_value = value
        self._num_acquired = 0
        super().__init__(value=value, io_loop=None)

    @property
    def max(self):
        '''The upper bound of the value.'''
        return self._max_value

    def set_max(self, value):
        '''Set the upper bound the value.'''
        if value < 0:
            raise ValueError('Maximum must be 0 or positive.')

        self._max_value = value

        while self.q.qsize() + self._num_acquired < self._max_value:
            self.q.put_nowait(None)

    def acquire(self, deadline=None):
        def increment_cb(future):
            if not future.cancelled() and not future.exception():
                self._num_acquired += 1

        future = super().acquire(deadline=deadline)

        future.add_done_callback(increment_cb)

        return future

    def release(self):
        # Copied and modified from toro
        """Increment :attr:`counter` and wake waiters based on :attr:`max`.
        """
        self._num_acquired -= 1

        if self._num_acquired < 0:
            raise ValueError('Semaphore released too many times.')

        while self.q.qsize() + self._num_acquired < self._max_value:
            self.q.put_nowait(None)

        if not self.locked():
            # No one was waiting on acquire(), so self.q.qsize() is positive
            self._unlocked.set()
