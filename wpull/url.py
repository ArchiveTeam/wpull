# encoding=utf-8
'''URLs.'''
import abc
import collections
import fnmatch
import functools
import itertools
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
        'url',
        'encoding',
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
    def parse(cls, string, default_scheme='http', encoding='utf8'):
        '''Parse and return a new info from the given URL.

        Returns:
            :class:`URLInfo`

        Raises:
            :class:`ValueError` if the URL is seriously malformed
        '''
        if not string:
            raise ValueError('Empty URL')

        assert isinstance(string, str)

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
            cls.normalize_query(url_split_result.query, encoding=encoding),
            url_split_result.fragment,
            url_split_result.username,
            url_split_result.password,
            cls.normalize_hostname(url_split_result.hostname),
            port,
            string,
            cls.normalize(url_split_result, encoding=encoding),
            wpull.util.normalize_codec_name(encoding),
        )

    @classmethod
    def normalize(cls, url_split_result, encoding='utf8'):
        '''Return a normalized URL string.'''
        if url_split_result.scheme not in ('http', 'https'):
            return url_split_result.geturl()

        default_port = cls.DEFAULT_PORTS.get(url_split_result.scheme)

        if default_port == url_split_result.port:
            host_with_port = cls.normalize_hostname(url_split_result.hostname)
        else:
            host_with_port = url_split_result.netloc.split('@', 1)[-1]
            if ':' in host_with_port:
                host, port = host_with_port.rsplit(':', 1)
                host_with_port = '{0}:{1}'.format(
                    cls.normalize_hostname(host), port)
            else:
                host_with_port = cls.normalize_hostname(host_with_port)

        return urllib.parse.urlunsplit([
            url_split_result.scheme,
            host_with_port,
            cls.normalize_path(url_split_result.path, encoding=encoding),
            cls.normalize_query(url_split_result.query, encoding=encoding),
            ''
        ])

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
            return quasi_quote(path, encoding='latin-1') or '/'
        else:
            return quote(path, encoding=encoding) or '/'

    @classmethod
    def normalize_query(cls, query, encoding='utf8'):
        '''Normalize the query.'''
        if not query:
            return

        query_list = split_query(query, keep_blank_values=True)
        query_test_str = ''.join(itertools.chain(*query_list))

        if is_percent_encoded(query_test_str):
            quote_func = functools.partial(
                quasi_quote_plus, encoding='latin-1')
        else:
            quote_func = functools.partial(quote_plus, encoding=encoding)

        return '&'.join([
            '='.join((
                quote_func(name),
                quote_func(value)
            ))
            for name, value in query_list])

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
    def __init__(self, enabled, page_requisites):
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
    def __init__(self, input_url_infos, enabled=False):
        self._enabled = enabled
        self._base_urls = list(
            [url_info.hostname for url_info in input_url_infos])

    def test(self, url_info, url_table_record):
        if self._enabled:
            return True

        if url_info.hostname in self._base_urls:
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
    '''Split the query string.'''
    new_list = []

    for pair in qs.split('&'):
        items = pair.split('=', 1)

        if len(items) == 0:
            continue

        if len(items) == 1:
            name = items[0]
            value = ''
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
UNESCAPED_CHARS = frozenset(' &=')


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
