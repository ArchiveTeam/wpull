# encoding=utf-8
'''URLs.'''
import collections
import fnmatch
import functools
import itertools
import mimetypes
import re
import string
import sys
import urllib.parse

import namedlist

from wpull.cache import LRUCache
import wpull.string


if sys.version_info < (2, 7):
    from wpull.backport import urlparse


RELAXED_SAFE_CHARS = '/!$&()*+,:;=@[]~'
'''Characters in URL path that should be safe to not escape.'''

RELAXED_SAFE_QUERY_KEYS_CHARS = '/!$()*+,:;?@[]~'
'''Characters in URL query keys that should be safe to not escape.'''

RELAXED_SAFE_QUERY_VALUE_CHARS = RELAXED_SAFE_QUERY_KEYS_CHARS + '='
'''Characters in URL query values that should be safe to not escape.'''


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
    ]
)


NormalizationParams = namedlist.namedtuple(
    'NormalizationParamsType',
    [
        ('sort_query', False),
        ('always_delim_query', False)
    ]
)
'''Parameters for URL normalization.

Args:
    sort_query (bool): Whether to sort the query string items.
    always_delim_query: Whether to always deliminate the key-value items where
        value is empty.
'''


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

    This class will attempt to percent-encode any URLs deemed to be not yet
    percent-encoded. Otherwise, it will attempt to percent-encode parts
    of the URL that should be percent-encoded. It will also uppercase the
    percent-encoding sequences.

    This class will convert hostnames to the proper IDNA ASCII sequences.

    This class is currently only specialized for HTTP protocols.
    '''
    DEFAULT_PORTS = {
        'http': 80,
        'https': 443,
    }

    cache = LRUCache(max_items=1000)

    @classmethod
    def parse(cls, string, default_scheme='http', encoding='utf8',
    normalization_params=None, use_cache=True):
        '''Parse and return a new info from the given URL.

        Args:
            string (str): The URL.
            default_scheme (str): The default scheme if not specified.
            encoding (str): The name of the encoding to be used for IRI
                support.
            normalization_params: Instance of :class:`NormalizationParams`
                describing further normalization settings.

        Returns:
            :class:`URLInfo`

        Raises:
            `ValueError`: The URL is seriously malformed.
        '''
        if not string:
            raise ValueError('Empty URL')

        assert isinstance(string, str)

        cache_key = (string, default_scheme, encoding, normalization_params)

        if use_cache:
            try:
                return cls.cache[cache_key]
            except KeyError:
                pass

        if normalization_params is None:
            normalization_params = NormalizationParams()

        url_split_result = urllib.parse.urlsplit(string)

        if not url_split_result.scheme:
            url_split_result = urllib.parse.urlsplit(
                '{0}://{1}'.format(default_scheme, string)
            )

        if url_split_result.scheme in ('http', 'https'):
            if string.startswith('//'):
                url_split_result = urllib.parse.urlsplit(
                '{0}:{1}'.format(url_split_result.scheme, string)
            )

            elif not url_split_result.hostname:
                raise ValueError('Missing hostname for HTTP protocol.')

        port = url_split_result.port

        if not port:
            port = 80 if url_split_result.scheme == 'http' else 443

        url_info = URLInfo(
            url_split_result.scheme,
            url_split_result.netloc,
            cls.normalize_path(url_split_result.path, encoding=encoding),
            cls.normalize_query(
                url_split_result.query, encoding=encoding,
                sort=normalization_params.sort_query,
                always_delim=normalization_params.always_delim_query,
            ),
            url_split_result.fragment,
            url_split_result.username,
            url_split_result.password,
            cls.normalize_hostname(url_split_result.hostname),
            port,
            string,
            wpull.string.normalize_codec_name(encoding),
        )

        if use_cache:
            cls.cache[cache_key] = url_info

        return url_info

    @classmethod
    def normalize_hostname(cls, hostname):
        '''Normalize the hostname.'''
        if hostname:
            if '[' in hostname \
            or ']' in hostname:
                # XXX: Python lib IPv6 checking can't get it right.
                raise ValueError('Failed to parse IPv6 URL correctly.')

            # Double encodes to work around issue #82 (Python #21103).
            return hostname\
                .encode('idna').decode('ascii')\
                .encode('idna').decode('ascii')
        else:
            return hostname

    @classmethod
    def normalize_path(cls, path, encoding='utf8'):
        '''Normalize the path.'''
        if path is None:
            return

        if is_percent_encoded(path):
            return flatten_path(
                quasi_quote(path, encoding='latin-1', safe=RELAXED_SAFE_CHARS)
            ) or '/'
        else:
            return flatten_path(
                quote(path, encoding=encoding, safe=RELAXED_SAFE_CHARS)
            ) or '/'

    @classmethod
    def normalize_query(cls, query, encoding='utf8',
    sort=False, always_delim=False):
        '''Normalize the query.

        Args:
            query (str): The query string.
            encoding (str): IRI encoding.
            sort (bool): If True, the items will be sorted.
            always_delim (bool): If True, the equal sign ``=`` deliminator
                will always be present for each key-value item.
        '''
        if not query:
            return

        query_list = split_query(query, keep_blank_values=True)
        query_test_str = ''.join(
            itertools.chain(*[(key, value or '') for key, value in query_list])
        )

        if is_percent_encoded(query_test_str):
            quote_func = functools.partial(
                quasi_quote_plus, encoding='latin-1')
        else:
            quote_func = functools.partial(quote_plus, encoding=encoding)

        if sort:
            query_list.sort()

        return '&'.join([
            '='.join((
                quote_func(name, safe=RELAXED_SAFE_QUERY_KEYS_CHARS),
                quote_func(value or '', safe=RELAXED_SAFE_QUERY_VALUE_CHARS)
            ))
            if value is not None or always_delim else
            quote_func(name)
            for name, value in query_list])

    @property
    def url(self):
        '''Return a normalized URL string.'''
        if self.scheme not in ('http', 'https'):
            url_split_result = urllib.parse.urlsplit(self.raw)
            return url_split_result.geturl()

        return urllib.parse.urlunsplit([
            self.scheme,
            self.hostname_with_port,
            self.path,
            self.query,
            ''
        ])

    def is_port_default(self):
        '''Return whether the URL is using the default port.'''
        if self.scheme in self.DEFAULT_PORTS:
            return self.DEFAULT_PORTS[self.scheme] == self.port

    def is_ipv6(self):
        '''Return whether the URL is IPv6.'''
        host_part = self.netloc.rsplit('@', 1)[-1]
        return '[' in host_part

    @property
    def hostname_with_port(self):
        '''Return the hostname with port.'''
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


def quote(string, safe='/', encoding='utf-8', errors='strict'):
    '''``urllib.parse.quote`` with Python 2 compatbility.'''
    if sys.version_info[0] == 2:
        # Backported behavior
        return urllib.parse.quote(
            string.encode(encoding, errors),
            safe.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.quote(string, safe, encoding, errors)


def quote_plus(string, safe='', encoding='utf-8', errors='strict'):
    '''``urllib.parse.quote_plus`` with Python 2 compatbility.'''
    if sys.version_info[0] == 2:
        # Backported behavior
        return urllib.parse.quote_plus(
            string.encode(encoding, errors),
            safe.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.quote_plus(string, safe, encoding, errors)


def unquote(string, encoding='utf-8', errors='strict'):
    '''``urllib.parse.unquote`` with Python 2 compatbility.'''
    if sys.version_info[0] == 2:
        return urllib.parse.unquote(
            string.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.unquote(string, encoding, errors)


def unquote_plus(string, encoding='utf-8', errors='strict'):
    '''``urllib.parse.unquote_plus`` with Python 2 compatbility.'''
    if sys.version_info[0] == 2:
        return urllib.parse.unquote_plus(
            string.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.unquote_plus(string, encoding, errors)


def quasi_quote(string, safe='/', encoding='latin-1', errors='strict'):
    '''Normalize a quoted URL path.'''
    return quote(
        unquote(string, encoding, errors),
        safe, encoding, errors
    )


def quasi_quote_plus(string, safe='', encoding='latin-1', errors='strict'):
    '''Normalize a quoted URL query string.'''
    return quote_plus(
        unquote_plus(string, encoding, errors),
        safe, encoding, errors
    )


def split_query(qs, keep_blank_values=False):
    '''Split the query string.

    Note for empty values: If an equal sign (``=``) is present, the value
    will be an empty string (``''``). Otherwise, the value will be ``None``::

        >>> split_query('a=&b', keep_blank_values=True)
        [('a', ''), ('b', None)]

    '''
    new_list = []

    for pair in qs.split('&'):
        items = pair.split('=', 1)

        if len(items) == 1:
            name = items[0]
            value = None
        else:
            name, value = items

        if keep_blank_values or value:
            new_list.append((name, value))

    return new_list


def uppercase_percent_encoding(string):
    '''Uppercases percent-encoded sequences.'''
    return re.sub(
        r'%[a-f0-9][a-f0-9]',
        lambda match: match.group(0).upper(),
        string)


PRINTABLE_CHARS = frozenset(
    string.digits + string.ascii_letters + string.punctuation
)
HEX_CHARS = frozenset(string.hexdigits)


def is_percent_encoded(url):
    '''Return whether the URL is percent-encoded.'''
    input_chars = frozenset(url)

    if not input_chars <= PRINTABLE_CHARS:
        return False

    for match_str in re.findall('%(..)', url):
        if not frozenset(match_str) <= HEX_CHARS:
            return False

    return True


def urljoin(base_url, url, allow_fragments=True):
    '''Join URLs like ``urllib.parse.urljoin`` but allow double-slashes.'''
    if url.startswith('//'):
        scheme = urllib.parse.urlsplit(base_url).scheme
        return urllib.parse.urljoin(
            base_url,
            '{0}:{1}'.format(scheme, url),
            allow_fragments=allow_fragments
        )
    else:
        return urllib.parse.urljoin(
            base_url, url, allow_fragments=allow_fragments)


def flatten_path(path, slashes=False):
    '''Flatten an absolute URL path by removing the dot segments.

    :func:`urllib.parse.urljoin` has some support for removing dot segments,
    but it is conservative and only removes them as needed.
    '''
    # Based on posixpath.normpath
    parts = path.split('/')

    new_parts = collections.deque()

    for part in parts:
        if part == '.' or (slashes and not part):
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
