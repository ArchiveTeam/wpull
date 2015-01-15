# encoding=utf-8
'''URL filters.'''
import abc
import fnmatch
import re

from wpull.url import URLInfo, schemes_similar, is_subdir


class BaseURLFilter(object, metaclass=abc.ABCMeta):
    '''Base class for URL filters.

    The Processor uses filters to determine whether a URL should be downloaded.
    '''
    @abc.abstractmethod
    def test(self, url_info, url_table_record):
        '''Return whether the URL should be downloaded.

        Args:
            url_info: :class:`.url.URLInfo`
            url_table_record: :class:`.item.URLRecord`

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
            * ``map`` (dict): A mapping from URLFilter class name (str) to
              the verdict (bool).
        '''
        passed = set()
        failed = set()
        test_dict = dict()

        for url_filter in self._url_filters:
            result = url_filter.test(url_info, url_table_record)
            test_dict[url_filter.__class__.__name__] = result

            if result:
                passed.add(url_filter)
            else:
                failed.add(url_filter)

        info = {
            'verdict': len(failed) == 0,
            'passed': passed,
            'failed': failed,
            'map': test_dict,
        }

        return info


class SchemeFilter(BaseURLFilter):
    '''Allow URL if the URL is in list.'''
    def __init__(self, allowed=('http', 'https', 'ftp')):
        self._allowed = allowed

    def test(self, url_info, url_table_record):
        return url_info.scheme in self._allowed


class HTTPSOnlyFilter(BaseURLFilter):
    '''Allow URL if the URL is HTTPS.'''
    def test(self, url_info, url_table_record):
        return url_info.scheme == 'https'


class FollowFTPFilter(BaseURLFilter):
    '''Follow links to FTP URLs.'''
    def __init__(self, follow=False):
        self._follow = follow

    def test(self, url_info, url_table_record):
        if url_info.scheme == 'ftp':
            if url_table_record.referrer and \
                    url_table_record.referrer_info.scheme in ('http', 'https'):
                return self._follow
            else:
                return True
        else:
            return True


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
    def __init__(self, max_depth, inline_max_depth=5):
        self._depth = max_depth
        self._inline_max_depth = inline_max_depth

    def test(self, url_info, url_table_record):
        if self._inline_max_depth and url_table_record.inline and \
                url_table_record.inline > self._inline_max_depth:
            return False

        if self._depth:
            if url_table_record.inline:
                # Allow exceeding level to allow fetching html pages with
                # frames, for example, but no more than that
                return url_table_record.level <= self._depth + 2
            else:
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
           and (
               url_info.scheme != top_url_info.scheme or
               url_info.port == top_url_info.port
        ):
            return is_subdir(top_url_info.path, url_info.path,
                             trailing_slash=True)

        return True


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
