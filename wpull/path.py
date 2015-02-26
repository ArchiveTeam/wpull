'''File names and paths.'''
import abc
import base64
import hashlib
import os
import re
import urllib.parse
import collections


class BasePathNamer(object, metaclass=abc.ABCMeta):
    '''Base class for path namers.'''
    @abc.abstractmethod
    def get_filename(self, url_info):
        '''Return the appropriate filename based on given URLInfo.'''


class PathNamer(BasePathNamer):
    '''Path namer that creates a directory hierarchy based on the URL.

    Args:
        root (str): The base path.
        index (str): The filename to use when the URL path does not indicate
            one.
        use_dir (bool): Include directories based on the URL path.
        cut (int): Number of leading directories to cut from the file path.
        protocol (bool): Include the URL scheme in the directory structure.
        hostname (bool): Include the hostname in the directory structure.
        safe_filename_args (dict): Keyword arguments for `safe_filename`.

    See also: :func:`url_to_filename`, :func:`url_to_dir_path`,
    :func:`safe_filename`.
    '''
    def __init__(self, root, index='index.html', use_dir=False, cut=None,
                 protocol=False, hostname=False, os_type='unix',
                 no_control=True, ascii_only=True,
                 case=None, max_filename_length=None):
        self._root = root
        self._index = index
        self._cut = cut
        self._protocol = protocol
        self._hostname = hostname
        self._use_dir = use_dir
        self._os_type = os_type
        self._no_control = no_control
        self._ascii_only = ascii_only
        self._case = case
        self._max_filename_length = max_filename_length

        if os.path.isfile(root):
            raise IOError('Root cannot be a file.')

    def get_filename(self, url_info):
        url = url_info.url
        alt_char = self._os_type == 'windows'
        parts = []

        if self._use_dir:
            dir_parts = url_to_dir_parts(
                url, self._protocol, self._hostname, alt_char=alt_char
            )

            for dummy in range(self._cut or 0):
                if dir_parts:
                    del dir_parts[0]

            parts.extend(dir_parts)

        parts.append(url_to_filename(
            url,
            '.listing' if url_info.scheme == 'ftp' else self._index,
            alt_char=alt_char
        ))

        if url_info.scheme == 'ftp':
            parts = [urllib.parse.unquote(part) for part in parts]

        parts = [self.safe_filename(part) for part in parts]

        return os.path.join(self._root, *parts)

    def safe_filename(self, part):
        '''Return a safe filename or file part.'''
        return safe_filename(
            part,
            os_type=self._os_type, no_control=self._no_control,
            ascii_only=self._ascii_only, case=self._case,
            max_length=self._max_filename_length,
            )


def url_to_filename(url, index='index.html', alt_char=False):
    '''Return a filename from a URL.

    Args:
        url (str): The URL.
        index (str): If a filename could not be derived from the URL path,
            use index instead. For example, ``/images/`` will return
            ``index.html``.
        alt_char (bool): If True, the character for the query deliminator
            will be ``@`` intead of ``?``.

    This function does not include the directories and does not sanitize
    the filename.

    Returns:
        str
    '''
    assert isinstance(url, str), 'Expect str. Got {}.'.format(type(url))
    url_split_result = urllib.parse.urlsplit(url)

    filename = url_split_result.path.split('/')[-1]

    if not filename:
        filename = index

    if url_split_result.query:
        if alt_char:
            query_delim = '@'
        else:
            query_delim = '?'

        filename = '{0}{1}{2}'.format(
            filename, query_delim, url_split_result.query
        )

    return filename


def url_to_dir_parts(url, include_protocol=False, include_hostname=False,
                     alt_char=False):
    '''Return a list of directory parts from a URL.

    Args:
        url (str): The URL.
        include_protocol (bool): If True, the scheme from the URL will be
            included.
        include_hostname (bool): If True, the hostname from the URL will be
            included.
        alt_char (bool): If True, the character for the port deliminator
            will be ``+`` intead of ``:``.

    This function does not include the filename and the paths are not
    sanitized.

    Returns:
        list
    '''
    assert isinstance(url, str), 'Expect str. Got {}.'.format(type(url))
    url_split_result = urllib.parse.urlsplit(url)

    parts = []

    if include_protocol:
        parts.append(url_split_result.scheme)

    if include_hostname:
        hostname = url_split_result.hostname

        if url_split_result.port:
            if alt_char:
                port_delim = '+'
            else:
                port_delim = ':'

            hostname = '{0}{1}{2}'.format(
                hostname, port_delim, url_split_result.port
            )

        parts.append(hostname)

    for path_part in url_split_result.path.split('/'):
        if path_part:
            parts.append(path_part)

    if not url.endswith('/') and parts:
        parts.pop()

    return parts


class PercentEncoder(collections.defaultdict):
    '''Percent encoder.'''
    # The percent-encoder was inspired from urllib.parse
    def __init__(self, unix=False, control=False, windows=False, ascii_=False):
        super().__init__()
        self.unix = unix
        self.control = control
        self.windows = windows
        self.ascii = ascii_

    def __missing__(self, char):
        assert isinstance(char, bytes), \
            'Expect bytes. Got {}.'.format(type(char))

        char_num = ord(char)

        if ((self.unix and char == b'/')
            or (self.control and
                    (0 <= char_num <= 31 or 128 <= char_num <= 159))
            or (self.windows and char in br'\|/:?"*<>')
            or (self.ascii and char_num > 127)):
            value = b'%' + base64.b16encode(char)
        else:
            value = char

        self[char] = value
        return value

    def quote(self, bytes_string):
        quoter = self.__getitem__
        return b''.join(
            [quoter(bytes_string[i:i + 1]) for i in range(len(bytes_string))]
        )


_encoder_cache = {}


def safe_filename(filename, os_type='unix', no_control=True, ascii_only=True,
                  case=None, encoding='utf8', max_length=None):
    '''Return a safe filename or path part.

    Args:
        filename (str): The filename or path component.
        os_type (str): If ``unix``, escape the slash. If ``windows``, escape
            extra Windows characters.
        no_control (bool): If True, escape control characters.
        ascii_only (bool): If True, escape non-ASCII characters.
        case (str): If ``lower``, lowercase the string. If ``upper``, uppercase
            the string.
        encoding (str): The character encoding.
        max_length (int): The maximum length of the filename.

    This function assumes that `filename` has not already been percent-encoded.

    Returns:
        str
    '''
    assert isinstance(filename, str), \
        'Expect str. Got {}.'.format(type(filename))

    if filename in ('.', os.curdir):
        new_filename = '%2E'
    elif filename in ('.', os.pardir):
        new_filename = '%2E%2E'
    else:
        unix = os_type == 'unix'
        windows = os_type == 'windows'
        encoder_args = (unix, no_control, windows, ascii_only)

        if encoder_args not in _encoder_cache:
            _encoder_cache[encoder_args] = PercentEncoder(
                unix=unix, control=no_control, windows=windows,
                ascii_=ascii_only
            )

        encoder = _encoder_cache[encoder_args]
        encoded_filename = filename.encode(encoding)
        new_filename = encoder.quote(encoded_filename).decode(encoding)

    if os_type == 'windows':
        if new_filename[-1] in ' .':
            new_filename = '{0}{1:02X}'.format(
                new_filename[:-1], new_filename[-1]
            )

    if max_length and len(new_filename) > max_length:
        hash_obj = hashlib.sha1(new_filename.encode(encoding))
        new_length = max(0, max_length - 8)
        new_filename = '{0}{1}'.format(
            new_filename[:new_length], hash_obj.hexdigest()[:8]
        )

    if case == 'lower':
        new_filename = new_filename.lower()
    elif case == 'upper':
        new_filename = new_filename.upper()

    return new_filename


def anti_clobber_dir_path(dir_path, suffix='.d'):
    '''Return a directory path free of filenames.

    Args:
        dir_path (str): A directory path.
        suffix (str): The suffix to append to the part of the path that is
             a file.

    Returns:
        str
    '''
    dir_path = os.path.normpath(dir_path)
    parts = dir_path.split(os.sep)

    for index in range(len(parts)):
        test_path = os.path.join(*parts[:index + 1])

        if os.path.isfile(test_path):
            parts[index] += suffix

            return os.path.join(*parts)

    return dir_path


def parse_content_disposition(text):
    '''Parse a Content-Disposition header value.'''
    match = re.search(r'filename\s*=\s*(.+)', text, re.IGNORECASE)

    if not match:
        return

    filename = match.group(1)

    if filename[0] in '"\'':
        match = re.match(r'(.)(.+)(?!\\)\1', filename)

        if match:
            filename = match.group(2).replace('\\"', '"')

            return filename

    else:
        filename = filename.partition(';')[0].strip()
        return filename
