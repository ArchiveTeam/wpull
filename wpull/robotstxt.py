import gettext
import logging
from wpull.thirdparty import robotexclusionrulesparser

from wpull.url import URLInfo


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class RobotsTxtPool(object):
    def __init__(self):
        self._parsers = {}

    def has_parser(self, url_info):
        key = self.url_info_key(url_info)
        return key in self._parsers

    def can_fetch(self, url_info, user_agent):
        key = self.url_info_key(url_info)

        parser = self._parsers[key]
        return parser.is_allowed(user_agent, url_info.url)

    def load_robots_txt(self, url_info, text):
        key = self.url_info_key(url_info)
        parser = robotexclusionrulesparser.RobotExclusionRulesParser()
        parser.parse(text)

        self._parsers[key] = parser

    @classmethod
    def url_info_key(cls, url_info):
        return (url_info.scheme, url_info.hostname, url_info.port)


class RobotsTxtSessionMixin(object):
    class RobotsState(object):
        not_checked = 1
        fetched = 2
        need_fetch = 3
        error = 4

    def __init__(self, *args, **kwargs):
        self._robots_txt_pool = kwargs.pop('robots_txt_pool', RobotsTxtPool())

        self._robots_attempts_remaining = 20
        self._robots_redirects_remaining = 5
        self._robots_redirect_url = None
        self._robots_state = self.RobotsState.not_checked
        self._robots_request = None

        super().__init__(*args, **kwargs)

    def should_fetch(self):
        if not super().should_fetch():
            return False

        if self._robots_state in (self.RobotsState.not_checked,
        self.RobotsState.fetched):
            ok = self._check_robots_txt_pool()
            if not ok:
                self._url_item.skip()
            return ok
        elif self._robots_state == self.RobotsState.need_fetch:
            return True
        else:
            return super().should_fetch()

    def _check_robots_txt_pool(self):
        url_info = self._next_url_info
        request = self._new_request_instance(url_info.url, url_info.encoding)
        user_agent = request.fields.get('user-agent', '')

        if not self._robots_txt_pool.has_parser(url_info):
            _logger.debug('robots.txt not in pool')
            self._robots_state = self.RobotsState.need_fetch
            return True

        self._robots_state = self.RobotsState.fetched

        if not self._robots_txt_pool.can_fetch(url_info, user_agent):
            _logger.debug('Cannot fetch {url} due to robots.txt'.format(
                url=url_info.url))
            return False
        else:
            return super().should_fetch()

    def new_request(self):
        if self._robots_state == self.RobotsState.need_fetch:
            if self._robots_redirect_url:
                self._robots_request = self._new_request_instance(
                    self._robots_redirect_url, 'latin-1')
                self._robots_redirect_url = None
            else:
                url_info = self._next_url_info
                url = URLInfo.parse('{0}://{1}:{2}/robots.txt'.format(
                    url_info.scheme, url_info.hostname, url_info.port)).url
                self._robots_request = self._new_request_instance(
                    url, url_info.encoding)

            _logger.debug('Making request for robots.txt')
            return self._robots_request

        return super().new_request()

    def handle_response(self, response):
        if self._robots_state == self.RobotsState.need_fetch:
            return self._handle_robots_response(response)
        else:
            return super().handle_response(response)

    def _handle_robots_response(self, response):
        _logger.debug('Handling robots.txt response.')

        if self._robots_attempts_remaining == 0:
            _logger.warning(_('Too many failed attempts to get robots.txt.'))
            self._waiter.reset()
            self._robots_state = self.RobotsState.error
        elif self._robots_redirects_remaining == 0:
            _logger.warning(_('Ignoring robots.txt redirect loop.'))
            self._waiter.reset()
            self._robots_state = self.RobotsState.error
        elif not response or 500 <= response.status_code <= 599:
            _logger.debug('Temporary error getting robots.txt.')
            self._robots_attempts_remaining -= 1
            self._waiter.increment()
        elif response.status_code in self._redirect_codes:
            _logger.debug('Got a redirect for robots.txt.')
            self._accept_empty(self._robots_request.url_info)
            self._robots_redirects_remaining -= 1
            self._robots_redirect_url = response.fields.get('location')
        else:
            self._robots_state = self.RobotsState.fetched

            if response.status_code == 200:
                self._accept_ok(response)
            else:
                self._accept_empty(self._robots_request.url_info)

    def _accept_ok(self, response):
        url_info = self._robots_request.url_info

        try:
            self._robots_txt_pool.load_robots_txt(
                url_info,
                response.body.content_segment())
        except ValueError:
            _logger.warning(
                _('Failed to parse {url} for robots exclusion rules. '
                    'Ignoring.').format(url_info.url))
            self._accept_empty(url_info)
        else:
            _logger.debug('Got a good robots.txt for {0}.'.format(
                url_info.url))

    def _accept_empty(self, url_info):
        _logger.debug('Got empty robots.txt for {0}.'.format(url_info.url))
        self._robots_txt_pool.load_robots_txt(url_info, '')
