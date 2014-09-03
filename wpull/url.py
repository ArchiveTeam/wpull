# encoding=utf-8
'''URL parsing based on WHATWG URL living spec.'''
import collections
from encodings import idna
import fnmatch
import itertools
import mimetypes
import re
import string
import urllib.parse

import tornado.netutil


DEFAULT_PORTS = {
    'http': 80,
    'https': 443,
    'ftp': 21,
}
'''Mapping of scheme to default port number.'''

URL_PATTERN = re.compile(
    r'(http|https|ftp)://([^/?#]+)([^?#]*)\??([^#]*)\#?(.*)', re.IGNORECASE)
'''Regex for matching something like a HTTP or FTP URL.'''

NETLOC_PATTERN = re.compile(r'([^@]*)(?:@|^)([^@]+?)(:(\d+)$|$)')
'''Regex for matching the netloc of a HTTP or FTP URL.'''

DEFAULT_ENCODE_SET = frozenset(b' "#<>?`')
'''Percent encoding set as defined by WHATWG URL living standard.

Does not include U+0000 to U+001F nor U+001F or above.
'''

PASSWORD_ENCODE_SET = DEFAULT_ENCODE_SET & frozenset(b'/@\\')
'''Encoding set for passwords.'''

USERNAME_ENCODE_SET = PASSWORD_ENCODE_SET & frozenset(b':')
'''Encoding set for usernames.'''

QUERY_KEY_ENCODE_SET = frozenset(b'"#<>?`+=')
'''Encoding set for query keys.

Doesn't include U+0020 so a replace can be made later.
'''

QUERY_VALUE_ENCODE_SET = frozenset(b'"#<>?`+')
'''Encoding set for query values.

Doesn't include U+0020 so a replace can be made later.
'''


_URLInfoType = collections.namedtuple(
    'URLInfoType',
    [
        'scheme',
        'netloc',
        'path',
        'query',
        'fragment',
        'username',
        'password',
        'hostname',
        'port',
        'raw',
        'encoding',
        'raw_hostname',
    ]
)


class URLInfo(_URLInfoType):
    '''A named tuple containing the parts of the URL.

    Attributes:
        scheme: The protocol (for example, HTTP, FTP)
        netloc: The "main" part of the URL typically indicating the location
            of the resource with associated metadata such as username or
            port number
        path: The path of where the resource can be found
        query: Additional parameters that adjust how the document is
            return to the client
        fragment: A location within the document
        username: The username for login
        password: The password for login
        hostname: The hostname or IP address or of the server, otherwise
            ``None``
        port: The socket port number, otherwise, ``None``
        raw: The raw string provided
        url: The normalized URL string
        encoding: The character encoding of the percent-encoded data (IRI).

    This class will attempt to percent-encode unacceptable characters.
    It will also uppercase the percent-encoding sequences.

    This class will convert hostnames to the proper IDNA ASCII sequences.

    This class is currently only specialized for HTTP/FTP protocols.
'''
    @classmethod
    def parse(cls, text, default_scheme='http', encoding='utf-8'):
        '''Parse and return a new info from the given URL.

        Args:
            string (str): The URL.
            default_scheme (str): The default scheme if not specified.
            encoding (str): The name of the encoding to be used for IRI
                support.

        Returns:
            :class:`URLInfo`

        Raises:
            `ValueError`: The URL is seriously malformed or unsupported.
        '''
        if not text:
            raise ValueError('Empty URL')

        assert isinstance(text, str), \
            'Expect str. Got {}.'.format(type(text))

        if '://' not in text:
            if text.startswith('//'):
                text = '{}:{}'.format(default_scheme, text)
            elif ':' not in text[:8]:
                text = '{}://{}'.format(default_scheme, text)

        match = URL_PATTERN.match(text)

        if not match:
            raise ValueError('Failed to parse HTTP or FTP URL: {}'
                             .format(repr(text)))

        scheme = (match.group(1) or default_scheme).lower()
        netloc = match.group(2)

        netloc_match = NETLOC_PATTERN.match(netloc)

        if not netloc_match:
            raise ValueError('Failed to parse netloc.')

        user_and_password = netloc_match.group(1)

        if user_and_password:
            username, dummy, password = user_and_password.partition(':')
        else:
            username = None
            password = None

        raw_hostname = netloc_match.group(2)
        hostname = normalize_hostname(raw_hostname)
        ipv6_result = check_ipv6(hostname)

        if ipv6_result == 'invalid':
            raise ValueError('Invalid IPv6 address.')
        elif ipv6_result == 'ok':
            hostname = hostname[1:-1]

        port = netloc_match.group(4)

        if port:
            port = int(port)

            if port > 65535:
                raise ValueError('Port number {} seems unreasonable.'
                                 .format(port))
        else:
            try:
                port = DEFAULT_PORTS[scheme]
            except KeyError as error:
                raise ValueError('Default port missing.') from error

        path = normalize_path(match.group(3), encoding=encoding)
        query = normalize_query(match.group(4), encoding=encoding)
        fragment = match.group(5)

        url_info = URLInfo(
            scheme,
            netloc,
            path,
            query,
            fragment,
            username,
            password,
            hostname,
            port,
            text,
            encoding,
            raw_hostname
        )

        return url_info

    @property
    def url(self):
        '''Return a normalized URL string.'''
        if not self.username:
            userpass = ''
        elif self.password:
            userpass = '{}:{}@'.format(self.username, self.password)
        else:
            userpass = '{}:@'.format(self.username)

        if self.query:
            query = '?{}'.format(self.query)
        else:
            query = ''

        return '{scheme}://{userpass}{host}{path}{query}'\
            .format(scheme=self.scheme, userpass=userpass,
                    host=self.hostname_with_port, path=self.path, query=query)

    def is_port_default(self):
        '''Return whether the URL is using the default port.'''
        if self.scheme in DEFAULT_PORTS:
            return DEFAULT_PORTS[self.scheme] == self.port

    def is_ipv6(self):
        '''Return whether the URL is IPv6.'''
        return self.raw_hostname[0] == '['

    @property
    def hostname_with_port(self):
        '''Return the hostname with optional port.'''
        hostname = self.hostname or ''
        assert '[' not in hostname
        assert ']' not in hostname

        if self.is_ipv6():
            hostname = '[{0}]'.format(hostname)

        if self.is_port_default() or not self.port:
            return hostname
        else:
            return '{0}:{1}'.format(hostname, self.port)

    def to_dict(self):
        '''Return the info as a ``dict``.'''
        return {
            'scheme': self.scheme,
            'netloc': self.netloc,
            'path': self.path,
            'query': self.query,
            'fragment': self.fragment,
            'username': self.username,
            'password': self.password,
            'hostname': self.hostname,
            'port': self.port,
            'raw': self.raw,
            'url': self.url,
            'encoding': self.encoding,
        }


def normalize(url, **kwargs):
    '''Normalize a URL.

    This function is a convenience function that is equivalent to::

        >>> URLInfo.parse('http://example.com').url
        'http://example.com'

    :seealso: :func:`URLInfo.parse`.
    '''
    return URLInfo.parse(url, **kwargs).url


def schemes_similar(scheme1, scheme2):
    '''Return whether URL schemes are similar.

    This function considers the following schemes to be similar:

    * HTTP and HTTPS

    '''
    if scheme1 == scheme2:
        return True

    if frozenset((scheme1, scheme2)) <= frozenset(('http', 'https')):
        return True

    return False


def is_subdir(base_path, test_path, trailing_slash=False, wildcards=False):
    '''Return whether the a path is a subpath of another.

    Args:
        base_path: The base path
        test_path: The path which we are testing
        trailing_slash: If True, the trailing slash is treated with importance.
            For example, ``/images/`` is a directory while ``/images`` is a
            file.
        wildcards: If True, globbing wildcards are matched against paths
    '''
    if trailing_slash:
        base_path = base_path.rsplit('/', 1)[0] + '/'
        test_path = test_path.rsplit('/', 1)[0] + '/'
    else:
        if not base_path.endswith('/'):
            base_path += '/'

        if not test_path.endswith('/'):
            test_path += '/'

    if wildcards:
        return fnmatch.fnmatchcase(test_path, base_path)
    else:
        return test_path.startswith(base_path)


class PercentEncoderMap(collections.defaultdict):
    '''Helper map for percent encoding.'''
    # This class is based on urllib.parse.Quoter
    def __init__(self, encode_set):
        self.encode_set = encode_set

    def __missing__(self, char):
        if char < 0x20 or char > 0x7E or char in self.encode_set:
            result = '%{:02X}'.format(char)
        else:
            result = chr(char)
        self[char] = result
        return result


_percent_encoder_map_cache = {}
'''Cache of :class:`PercentEncoderMap`.'''


def percent_encode(text, encode_set=DEFAULT_ENCODE_SET, encoding='utf-8'):
    '''Percent encode text.

    Unlike Python's ``quote``, this function accepts a blacklist instead of
    a whitelist of safe characters.
    '''
    byte_string = text.encode(encoding)

    try:
        mapping = _percent_encoder_map_cache[encode_set]
    except KeyError:
        mapping = _percent_encoder_map_cache[encode_set] = PercentEncoderMap(
            encode_set).__getitem__

    return ''.join([mapping(char) for char in byte_string])


def percent_encode_plus(text, encode_set=QUERY_KEY_ENCODE_SET,
                        encoding='utf-8'):
    '''Percent encode text for query strings.

    Unlike Python's ``quote_plus``, this function accepts a blacklist instead
    of a whitelist of safe characters.
    '''
    if ' ' not in text:
        return percent_encode(text, encode_set, encoding)
    else:
        result = percent_encode(text, encode_set, encoding)
        return result.replace(' ', '+')


percent_decode = urllib.parse.unquote
percent_decode_plus = urllib.parse.unquote_plus


def split_query(qs, keep_blank_values=False):
    '''Split the query string.

    Note for empty values: If an equal sign (``=``) is present, the value
    will be an empty string (``''``). Otherwise, the value will be ``None``::

        >>> list(split_query('a=&b', keep_blank_values=True))
        [('a', ''), ('b', None)]

    '''
    for pair in qs.split('&'):
        name, delim, value = pair.partition('=')

        if not delim and keep_blank_values:
            value = None

        if keep_blank_values or value:
            yield (name, value)


def uppercase_percent_encoding(text):
    '''Uppercases percent-encoded sequences.'''
    if '%' not in text:
        return text

    return re.sub(
        r'%[a-f0-9][a-f0-9]',
        lambda match: match.group(0).upper(),
        text)


def normalize_hostname(hostname):
    '''Normalizes a hostname so that it is ASCII and valid domain name.'''
    result = idna.nameprep(hostname).encode('idna').decode('ascii')

    try:
        idna.ToUnicode(result)
    except (ValueError, TypeError, IndexError) as error:
        raise ValueError('Non-roundtrip IDNA.') from error
    else:
        return result


_is_valid_ip = tornado.netutil.is_valid_ip


def check_ipv6(hostname):
    '''Check if raw hostname is actually a IPv6 address.

    Returns:
        str: ``not``, ``ok``, ``invalid``
    '''
    if '[' in hostname or ']' in hostname:
        content = hostname[1:-1]

        if '[' in content or ']' in content:
            return 'invalid'

        return 'ok' if _is_valid_ip(content) else 'invalid'
    else:
        return 'not'


def normalize_path(path, encoding='utf-8'):
    '''Normalize a path string.

    Flattens a path by removing dot parts,
    percent-encodes unacceptable characters and ensures percent-encoding is
    uppercase.
    '''
    if not path.startswith('/'):
        path = '/' + path
    path = percent_encode(flatten_path(path), encoding=encoding)
    return uppercase_percent_encoding(path)


def normalize_query(text, encoding='utf-8'):
    '''Normalize a query string.

    Percent-encodes unacceptable characters and ensures percent-encoding is
    uppercase.
    '''
    items = []

    for key, value in split_query(text, True):
        key = percent_encode_plus(key, encode_set=QUERY_KEY_ENCODE_SET,
                                  encoding=encoding)
        if value is not None:
            value = percent_encode_plus(value, encode_set=QUERY_VALUE_ENCODE_SET,
                                        encoding=encoding)
            items.append('{}={}'.format(key, value))
        else:
            items.append(key)

    return uppercase_percent_encoding('&'.join(items))


def query_to_map(text):
    '''Return a mapping from query key to value lists.'''
    dict_obj = {}

    for key, value in split_query(text, True):
        if key not in dict_obj:
            dict_obj[key] = []

        if value:
            dict_obj[key].append(value.replace('+', ' '))
        else:
            dict_obj[key].append('')

    return query_to_map(text)


def urljoin(base_url, url, allow_fragments=True):
    '''Join URLs like ``urllib.parse.urljoin`` but allow double-slashes.'''
    assert '://' in base_url, 'base_url {} not a absolute URL'.format(base_url)

    if url.startswith('//'):
        scheme = re.match(r'(\w+)://', base_url).group(1)
        return urllib.parse.urljoin(
            base_url,
            '{0}:{1}'.format(scheme, url),
            allow_fragments=allow_fragments
        )
    else:
        return urllib.parse.urljoin(
            base_url, url, allow_fragments=allow_fragments)


def flatten_path(path, strip_slashes=False):
    '''Flatten an absolute URL path by removing the dot segments.

    :func:`urllib.parse.urljoin` has some support for removing dot segments,
    but it is conservative and only removes them as needed.

    Arguments:
        path (str): The URL path.
        strip_slashes (bool): If True, the leading and trailing slashes are
            removed.
    '''
    # Based on posixpath.normpath
    parts = path.split('/')

    new_parts = collections.deque()

    for part in parts:
        if part == '.' or (strip_slashes and not part):
            continue
        elif part != '..':
            new_parts.append(part)
        elif len(new_parts) > 1:
            new_parts.pop()

    return '/'.join(new_parts)


_mimetypes_db = mimetypes.MimeTypes()
MIMETYPES = frozenset(
    itertools.chain(
        _mimetypes_db.types_map[0].values(),
        _mimetypes_db.types_map[1].values(),
        ['text/javascript']
    )
)
ALPHANUMERIC_CHARS = frozenset(string.ascii_letters + string.digits)
NUMERIC_CHARS = frozenset(string.digits)
COMMON_TLD = frozenset(['com', 'org', 'net', 'int', 'edu', 'gov', 'mil'])


# These "likely link" functions are based from
# https://github.com/internetarchive/heritrix3/
# blob/339e6ec87a7041f49c710d1d0fb94be0ec972ee7/commons/src/
# main/java/org/archive/util/UriUtils.java


def is_likely_link(text):
    '''Return whether the text is likely to be a link.

    This function assumes that leading/trailing whitespace has already been
    removed.

    Returns:
        bool
    '''
    text = text.lower()

    # Check for absolute or relative URLs
    if (
        text.startswith('http://')
        or text.startswith('https://')
        or text.startswith('ftp://')
        or text.startswith('/')
        or text.startswith('//')
        or text.endswith('/')
        or text.startswith('../')
    ):
        return True

    # Check if it has a alphanumeric file extension and not a decimal number
    dummy, dot, file_extension = text.rpartition('.')

    if dot and file_extension and len(file_extension) <= 4:
        file_extension_set = frozenset(file_extension)

        if file_extension_set \
           and file_extension_set <= ALPHANUMERIC_CHARS \
           and not file_extension_set <= NUMERIC_CHARS:
            if file_extension in COMMON_TLD:
                return False

            file_type = mimetypes.guess_type(text, strict=False)[0]

            if file_type:
                return True
            else:
                return False


def is_unlikely_link(text):
    '''Return whether the text is likely to cause false positives.

    This function assumes that leading/trailing whitespace has already been
    removed.

    Returns:
        bool
    '''
    # Check for string concatenation in JavaScript
    if text[:1] in ',;+:' or text[-1:] in '.,;+:':
        return True

    if text[:1] == '.' \
       and not text.startswith('./') \
       and not text.startswith('../'):
        return True

    # Check for unusual characters
    if re.search(r'''[$()'"[\]{}|]''', text):
        return True

    if text in ('/', '//'):
        return True

    if '//' in text and '://' not in text and not text.startswith('//'):
        return True

    # Forbid strings like mimetypes
    if text in MIMETYPES:
        return True
