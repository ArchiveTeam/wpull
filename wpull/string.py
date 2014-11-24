# encoding=utf-8
'''String and binary data functions.'''
import codecs
import itertools

from wpull.thirdparty.dammit import UnicodeDammit, EncodingDetector


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
    else:
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
    else:
        return instance


def normalize_codec_name(name):
    '''Return the Python name of the encoder/decoder

    Returns:
        str, None
    '''
    name = UnicodeDammit.CHARSET_ALIASES.get(name.lower(), name)

    try:
        return codecs.lookup(name).name
    except (LookupError, TypeError):
        # TypeError occurs when name contains \x00
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

        if candidate == 'ascii' and fallback != 'ascii':
            # it's never ascii :)
            # Falling back on UTF-8/CP-1252/Latin-1 reduces chance of
            # failure
            continue

        if try_decoding(data, candidate):
            return candidate

    raise ValueError('Unable to detect encoding.')


def try_decoding(data, encoding):
    '''Return whether the Python codec could decode the data.'''
    try:
        data.decode(encoding, 'strict')
    except UnicodeError:
        # Data under 16 bytes is very unlikely to be truncated
        if len(data) > 16:
            for trim in (1, 2, 3):
                trimmed_data = data[:-trim]
                if trimmed_data:
                    try:
                        trimmed_data.decode(encoding, 'strict')
                    except UnicodeError:
                        continue
                    else:
                        return True
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

    return format_str.format(num=num, unit='TiB')


ALL_BYTES = bytes(bytearray(range(256)))
CONTROL_BYTES = bytes(bytearray(
    itertools.chain(range(0, 32), range(127, 256))
))


def printable_bytes(data):
    '''Remove any bytes that is not printable ASCII.

    This function is intended for sniffing content types such as UTF-16
    encoded text.
    '''
    return data.translate(ALL_BYTES, CONTROL_BYTES)


def printable_str(text, keep_newlines=False):
    '''Escape any control or non-ASCII characters from string.

    This function is intended for use with strings from an untrusted
    source such as writing to a console or writing to logs. It is
    designed to prevent things like ANSI escape sequences from
    showing.

    Use :func:`repr` or :func:`ascii` instead for things such as
    Exception messages.
    '''
    if isinstance(text, str):
        new_text = ascii(text)[1:-1]
    else:
        new_text = ascii(text)

    if keep_newlines:
        new_text = new_text.replace('\\r', '\r').replace('\\n', '\n')

    return new_text


def coerce_str_to_ascii(string):
    '''Force the contents of the string to be ASCII.

    Anything not ASCII will be replaced with with a replacement character.

    .. deprecated :: 0.1002
       Use :func:`printable_str` instead.
    '''
    return string.encode('ascii', 'replace').decode('ascii')
