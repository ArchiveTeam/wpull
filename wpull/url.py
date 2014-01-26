# encoding=utf-8
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


URLInfoType = collections.namedtuple(
    'URLInfoTuple',
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

KNOWN_SCHEMES = frozenset(['file', 'ftp', 'gopher', 'hdl', 'http', 'https',
    'imap', 'mailto', 'mms', 'news', 'nntp', 'prospero', 'rsync', 'rtsp',
    'rtspu', 'sftp', 'shttp', 'sip', 'sips', 'snews', 'svn', 'svn+ssh',
    'telnet', 'wais'])


class URLInfo(URLInfoType):
    DEFAULT_PORTS = {
        'http': 80,
        'https': 443,
    }

    @classmethod
    def parse(cls, string, default_scheme='http', encoding='utf8'):
        if not string:
            raise ValueError('Empty URL')

        assert isinstance(string, str)

        url_split_result = urllib.parse.urlsplit(string, scheme=default_scheme)

        if not url_split_result.hostname \
        and (url_split_result.scheme in ('http', 'https') \
        or (sys.version_info < (2, 7) \
        and url_split_result.scheme not in KNOWN_SCHEMES)):
            url_split_result = urllib.parse.urlsplit(
               default_scheme + '://' + string)

        if url_split_result.scheme in ('http', 'https') \
        and not url_split_result.hostname:
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
        if hostname:
            return hostname.encode('idna').decode('ascii')
        else:
            return hostname

    @classmethod
    def normalize_path(cls, path, encoding='utf8'):
        if path is None:
            return

        if is_percent_encoded(path):
            return quasi_quote(path, encoding='latin-1') or '/'
        else:
            return quote(path, encoding=encoding) or '/'

    @classmethod
    def normalize_query(cls, query, encoding='utf8'):
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
    @abc.abstractmethod
    def test(self, url_info, url_table_record):
        pass


class HTTPFilter(BaseURLFilter):
    def test(self, url_info, url_table_record):
        return url_info.scheme in ('http', 'https')


class BackwardDomainFilter(BaseURLFilter):
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
        for domain in domain_list:
            if test_domain.endswith(domain):
                return True


class HostnameFilter(BaseURLFilter):
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
    def __init__(self, max_depth):
        self._depth = max_depth

    def test(self, url_info, url_table_record):
        if self._depth:
            return url_table_record.level <= self._depth
        else:
            return True


class TriesFilter(BaseURLFilter):
    def __init__(self, max_tries):
        self._tries = max_tries

    def test(self, url_info, url_table_record):
        if self._tries:
            return url_table_record.try_count < self._tries
        else:
            return True


class ParentFilter(BaseURLFilter):
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
    if scheme1 == scheme2:
        return True

    if frozenset((scheme1, scheme2)) <= frozenset(('http', 'https')):
        return True

    return False


def is_subdir(base_path, test_path, trailing_slash=False, wildcards=False):
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
    if sys.version_info[0] == 2:
        # Backported behavior
        return urllib.parse.quote(
            string.encode(encoding, errors),
            safe.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.quote(string, safe, encoding, errors)


def quote_plus(string, safe='', encoding='utf-8', errors='strict'):
    if sys.version_info[0] == 2:
        # Backported behavior
        return urllib.parse.quote_plus(
            string.encode(encoding, errors),
            safe.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.quote_plus(string, safe, encoding, errors)


def unquote(string, encoding='utf-8', errors='strict'):
    if sys.version_info[0] == 2:
        return urllib.parse.unquote(
            string.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.unquote(string, encoding, errors)


def unquote_plus(string, encoding='utf-8', errors='strict'):
    if sys.version_info[0] == 2:
        return urllib.parse.unquote_plus(
            string.encode(encoding, errors)
        ).decode(encoding, errors)
    else:
        return urllib.parse.unquote_plus(string, encoding, errors)


def quasi_quote(string, safe='/', encoding='latin-1', errors='strict'):
    return quote(
        unquote(string, encoding, errors),
        safe, encoding, errors
    )


def quasi_quote_plus(string, safe='', encoding='latin-1', errors='strict'):
    return quote_plus(
        unquote_plus(string, encoding, errors),
        safe, encoding, errors
    )


def split_query(qs, keep_blank_values=False):
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
    return re.sub(
        r'%[a-f0-9][a-f0-9]',
        lambda match: match.group(0).upper(),
        string)


def is_percent_encoded(url):
    input_chars = frozenset(url)
    printable_chars = frozenset(string.printable)
    hex_chars = frozenset(string.hexdigits)

    if not input_chars <= printable_chars:
        return False

    if frozenset(' &=') & input_chars:
        return False

    for match_str in re.findall('%(..)', url):
        if not frozenset(match_str) <= hex_chars:
            return False

    return True
