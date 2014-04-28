# encoding=utf-8
'''String and binary data functions.'''
import codecs
import itertools

from bs4.dammit import UnicodeDammit, EncodingDetector


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


def fallback_decode(data, encoding='utf-8', fallback_encoding='latin-1'):
    '''Decode string with fallback encoding.

    Returns:
        tuple: First item is the text. Second item is the encoding name.
    '''
    try:
        return (data.decode(encoding), encoding)
    except UnicodeError:
        return (data.decode(fallback_encoding), encoding)
