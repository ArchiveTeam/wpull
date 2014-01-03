import abc
import collections
import re
import urllib.parse


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
    ]
)


class URLInfo(URLInfoType):
    @classmethod
    def parse(cls, string, default_scheme='http'):
        url_split_result = urllib.parse.urlsplit(string, scheme=default_scheme)

        if not url_split_result.hostname:
            url_split_result = urllib.parse.urlsplit(
               default_scheme + '://' + string)

        port = url_split_result.port

        if not port:
            port = 80 if url_split_result.scheme == 'http' else 443

        return URLInfo(
            url_split_result.scheme,
            url_split_result.netloc,
            url_split_result.path or '/',
            url_split_result.query,
            url_split_result.fragment,
            url_split_result.username,
            url_split_result.password,
            url_split_result.hostname,
            port,
            string,
            cls.normalize(url_split_result),
        )

    @classmethod
    def normalize(cls, url_split_result):
        host_with_port = url_split_result.netloc.split('@', 1)[-1]
        return urllib.parse.urlunsplit([
            url_split_result.scheme,
            host_with_port,
            url_split_result.path or '/',
            url_split_result.query,
            b''
        ])


class BaseURLFilter(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def test(self, url_info, url_table_record):
        pass


class BackwardDomainFilter(BaseURLFilter):
    def __init__(self, accepted=None, rejected=None):
        self._accepted = accepted
        self._rejected = rejected

    def test(self, url_info, url_table_record):
        test_domain = url_info.hostname
        if self._accepted:
            if not self.match(self._accepted, test_domain):
                return False

        if self._rejected:
            if self.match(self._rejected, test_domain):
                return False

        return True

    @classmethod
    def match(cls, domain_list, test_domain):
        for domain in domain_list:
            if test_domain.lower().endswith(domain):
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
    def __init__(self, input_url_infos):
        self._base_urls = list(
            [self.parse_url_base(url_info) for url_info in input_url_infos])

    def test(self, url_info, url_table_record):
        if url_table_record.inline:
            return True

        return self._match_any(url_info)

    def _match_any(self, url_info):
        for hostname, port, base_path in self._base_urls:
            if hostname == url_info.hostname.lower() \
            and port == url_info.port \
            and url_info.path.startswith(base_path):
                return True

    @classmethod
    def parse_url_base(cls, url_info):
        path = url_info.path.rsplit('/', 1)[0] + '/'

        return (
            url_info.hostname.lower(),
            url_info.port,
            path
        )


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
