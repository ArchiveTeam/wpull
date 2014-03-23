# encoding=utf-8
'''URLs.'''
import abc
import collections
import fnmatch
import functools
import itertools
import namedlist
import re
import string
import sys
import urllib.parse

import wpull.util


if sys.version_info < (2, 7):
    from wpull.backport import urlparse


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
    '''
    DEFAULT_PORTS = {
        'http': 80,
        'https': 443,
    }

    @classmethod
    def parse(cls, string, default_scheme='http', encoding='utf8',
    normalization_params=None):
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
            :class:`ValueError` if the URL is seriously malformed
        '''
        if not string:
            raise ValueError('Empty URL')

        assert isinstance(string, str)

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

        return URLInfo(
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
            wpull.util.normalize_codec_name(encoding),
        )

    @classmethod
    def normalize_hostname(cls, hostname):
        '''Normalize the hostname.'''
        if hostname:
            return hostname.encode('idna').decode('ascii')
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
                quote_func(name),
                quote_func(value or '')
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

    @property
    def hostname_with_port(self):
        '''Return the hostname with port.'''
        hostname = self.hostname or ''

        if ':' in hostname:
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


class BaseURLFilter(object, metaclass=abc.ABCMeta):
    '''Base class for URL filters.

    The Processor uses filters to determine whether a URL should be downloaded.
    '''
    @abc.abstractmethod
    def test(self, url_info, url_table_record):
        '''Return whether the URL should be downloaded.

        Args:
            url_info: :class:`URLInfo`
            url_table_record: :class:`.database.URLRecord`

        Returns:
            bool: If True, the fitler passed and the URL should be downloaded.
        '''
        pass


class DemuxURLFilter(BaseURLFilter):
    '''Puts multiple url filters into one.'''
    def __init__(self, url_filters):
        self._url_filters = url_filters

    def test(self, url_info, url_table_record):
        return self.test_info(url_info, url_table_record)['verdict']

    def test_info(self, url_info, url_table_record):
        '''Returns info about which filters passed or failed.

        Returns:
            dict: A dict containing the keys:

            * ``verdict`` (bool): Whether all the tests passed.
            * ``passed`` (set): A set of URLFilters that passed.
            * ``failed`` (set): A set of URLFilters that failed.
        '''
        passed = set()
        failed = set()

        for url_filter in self._url_filters:
            result = url_filter.test(url_info, url_table_record)

            if result:
                passed.add(url_filter)
            else:
                failed.add(url_filter)

        info = {
            'verdict': len(failed) == 0,
            'passed': passed,
            'failed': failed,
        }

        return info


class HTTPFilter(BaseURLFilter):
    '''Allow URL if the URL is HTTP or HTTPS.'''
    def test(self, url_info, url_table_record):
        return url_info.scheme in ('http', 'https')


class HTTPSOnlyFilter(BaseURLFilter):
    '''Allow URL if the URL is HTTPS.'''
    def test(self, url_info, url_table_record):
        return url_info.scheme == 'https'


class BackwardDomainFilter(BaseURLFilter):
    '''Return whether the hostname matches a list of hostname suffixes.'''
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        test_domain = url_info.hostname
        if self._accepted and not self.match(self._accepted, test_domain):
            return False

        if self._rejected and self.match(self._rejected, test_domain):
            return False

        return True

    @classmethod
    def match(cls, domain_list, test_domain):
        if not test_domain:
            return False

        for domain in domain_list:
            if test_domain.endswith(domain):
                return True


class HostnameFilter(BaseURLFilter):
    '''Return whether the hostname matches exactly in a list.'''
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        test_domain = url_info.hostname
        if self._accepted and not test_domain in self._accepted:
            return False

        if self._rejected and test_domain in self._rejected:
            return False

        return True


class RecursiveFilter(BaseURLFilter):
    '''Return ``True`` if recursion is used.'''
    def __init__(self, enabled=False, page_requisites=False):
        self._enabled = enabled
        self._page_requisites = page_requisites

    def test(self, url_info, url_table_record):
        if url_table_record.level == 0:
            return True
        if url_table_record.inline:
            if self._page_requisites:
                return True
        else:
            if self._enabled:
                return True


class LevelFilter(BaseURLFilter):
    '''Allow URLs up to a level of recursion.'''
    def __init__(self, max_depth):
        self._depth = max_depth

    def test(self, url_info, url_table_record):
        if self._depth:
            return url_table_record.level <= self._depth
        else:
            return True


class TriesFilter(BaseURLFilter):
    '''Allow URLs that have been attempted up to a limit of tries.'''
    def __init__(self, max_tries):
        self._tries = max_tries

    def test(self, url_info, url_table_record):
        if self._tries:
            return url_table_record.try_count < self._tries
        else:
            return True


class ParentFilter(BaseURLFilter):
    '''Filter URLs that descend up parent paths.'''
    def test(self, url_info, url_table_record):
        if url_table_record.inline:
            return True

        if url_table_record.top_url:
            top_url_info = URLInfo.parse(url_table_record.top_url)
        else:
            top_url_info = url_info

        if schemes_similar(url_info.scheme, top_url_info.scheme) \
        and url_info.hostname == top_url_info.hostname \
        and url_info.port == top_url_info.port:
            return is_subdir(top_url_info.path, url_info.path,
                trailing_slash=True)

        return False


class SpanHostsFilter(BaseURLFilter):
    '''Filter URLs that go to other hostnames.'''
    def __init__(self, input_url_infos, enabled=False,
    page_requisites=False, linked_pages=False):
        self._enabled = enabled
        self._page_requisites = page_requisites
        self._linked_pages = linked_pages
        self._base_urls = frozenset(
            [url_info.hostname for url_info in input_url_infos]
        )

    def test(self, url_info, url_table_record):
        if self._enabled:
            return True

        if url_info.hostname in self._base_urls:
            return True

        if self._page_requisites and url_table_record.inline:
            return True

        if self._linked_pages and url_table_record.referrer \
        and url_table_record.referrer_info.hostname in self._base_urls:
            return True


class RegexFilter(BaseURLFilter):
    '''Filter URLs that match a regular expression.'''
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        if self._accepted and not re.search(self._accepted, url_info.url):
            return False

        if self._rejected and re.search(self._rejected, url_info.url):
            return False

        return True


class DirectoryFilter(BaseURLFilter):
    '''Filter URLs that match a directory path part.'''
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        if self._accepted and not self._is_accepted(url_info):
            return False

        if self._rejected and self._is_rejected(url_info):
            return False

        return True

    def _is_accepted(self, url_info):
        for dirname in self._accepted:
            if is_subdir(dirname, url_info.path, wildcards=True):
                return True

    def _is_rejected(self, url_info):
        for dirname in self._rejected:
            if is_subdir(dirname, url_info.path, wildcards=True):
                return True


class BackwardFilenameFilter(BaseURLFilter):
    '''Filter URLs that match the filename suffixes.'''
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        test_filename = url_info.path.rsplit('/', 1)[-1]

        if not test_filename:
            return True

        if self._accepted:
            if self._rejected:
                return self.match(self._accepted, test_filename)\
                    and not self.match(self._rejected, test_filename)
            else:
                return self.match(self._accepted, test_filename)

        elif self._rejected and self.match(self._rejected, test_filename):
            return False

        return True

    @classmethod
    def match(cls, suffix_list, test_filename):
        if not test_filename:
            return False

        for suffix in suffix_list:
            match = re.search(fnmatch.translate(suffix), test_filename)
            if match:
                return True


def normalize(url, **kwargs):
    '''Normalize a URL.

    This function is a convenience function that is equivalent to::

        >>> URLInfo.parse('http://example.com').url
        'http://example.com'

    :seealso: :func:`URLInfo.parse`.
    '''
    return URLInfo.parse(url, **kwargs).url


RELAXED_SAFE_CHARS = '/!$&()*+,:;=@~'
'''Characters in URL path that should be safe to not escape.'''


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

        if len(items) == 0:
            continue

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


PRINTABLE_CHARS = frozenset(string.printable)
HEX_CHARS = frozenset(string.hexdigits)
UNESCAPED_CHARS = frozenset(' ')


def is_percent_encoded(url):
    '''Return whether the URL is percent-encoded.'''
    input_chars = frozenset(url)

    if not input_chars <= PRINTABLE_CHARS:
        return False

    if UNESCAPED_CHARS & input_chars:
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
