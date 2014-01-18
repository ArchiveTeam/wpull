import gettext
import logging
import robotexclusionrulesparser

from wpull.url import URLInfo


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class RobotsTxtPool(object):
    def __init__(self):
        self._parsers = {}

    def has_parser(self, request):
        key = self.url_info_key(request.url_info)
        return key in self._parsers

    def can_fetch(self, request):
        key = self.url_info_key(request.url_info)

        parser = self._parsers[key]
        return parser.is_allowed(request.fields.get('user-agent', ''),
            request.url_info.url)

    def load_robots_txt(self, url_info, text):
        key = self.url_info_key(url_info)
        parser = robotexclusionrulesparser.RobotExclusionRulesParser()
        parser.parse(text)

        self._parsers[key] = parser

    @classmethod
    def url_info_key(cls, url_info):
        return (url_info.scheme, url_info.hostname, url_info.port)


class RobotsTxtNotLoaded(Exception):
    pass


class RobotsTxtSubsession(object):
    class Result(object):
        done = 1
        redirect = 2
        retry = 3
        fail = 4

    def __init__(self, robots_txt_pool, request_factory,
    redirect_status_codes=(301, 302, 303, 307, 308)):
        self._robots_txt_pool = robots_txt_pool
        self._request = None
        self._attempts_remaining = 20
        self._redirects_remaining = 5
        self._redirect_url = None
        self._request_factory = request_factory
        self._redirect_status_codes = redirect_status_codes

    def can_fetch(self, request):
        if not self._robots_txt_pool.has_parser(request):
            raise RobotsTxtNotLoaded()

        if not self._robots_txt_pool.can_fetch(request):
            _logger.debug('Cannot fetch {url} due to robots.txt'.format(
                url=request.url_info.url))
            return False
        else:
            return True

    def rewrite_request(self, request):
        url_info = request.url_info

        if self._redirect_url:
            self._request = self._request_factory(self._redirect_url)
            self._redirect_url = None
        else:
            url = URLInfo.parse('{0}://{1}:{2}/robots.txt'.format(
                url_info.scheme, url_info.hostname, url_info.port)).url
            self._request = self._request_factory(url)

        return self._request

    def check_response(self, response):
        if self._attempts_remaining == 0:
            _logger.warning(_('Too many failed attempts to get robots.txt.'))
            return self.Result.fail

        if self._redirects_remaining == 0:
            _logger.warning(_('Ignoring robots.txt redirect loop.'))
            return self.Result.done

        if not response or 500 <= response.status_code <= 599:
            self._attempts_remaining -= 1
            return self.Result.retry
        elif response.status_code in self._redirect_status_codes:
            self._accept_empty(self._request.url_info)
            self._redirects_remaining -= 1
            redirect_url = response.fields.get('location')
            return self._parse_redirect_url(redirect_url)
        else:
            self._attempts_remaining = 20
            self._redirects_remaining = 5
            if response.status_code == 200:
                self._accept_ok(response)
                return self.Result.done
            else:
                self._accept_empty(self._request.url_info)
                return self.Result.done

    def _accept_ok(self, response):
        try:
            self._robots_txt_pool.load_robots_txt(self._request.url_info,
                response.body.content_segment())
        except ValueError:
            _logger.warning(_('Failed to parse {url}. Ignoring.').format(
                self._request.url_info.url))
            self._accept_empty(self._request.url_info)

    def _accept_empty(self, url_info):
        self._robots_txt_pool.load_robots_txt(url_info, '')

    def _parse_redirect_url(self, url):
        if url:
            self._redirect_url = url
            return self.Result.redirect

        self._accept_empty(self._request.url_info)
        return self.Result.done
