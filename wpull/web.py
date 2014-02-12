# encoding=utf-8
'''Advanced HTTP handling.'''
import gettext
import logging
import tornado.gen

from wpull.conversation import BaseClient
from wpull.errors import ProtocolError
from wpull.http import Request
from wpull.robotstxt import RobotsState, RobotsDenied
from wpull.url import URLInfo
import wpull.url


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class RedirectTracker(object):
    '''Keeps track of HTTP document URL redirects.

    Args:
        max_redirects (int): The maximum number of redirects to allow.
        codes: The HTTP status codes indicating a redirect where the method
            can change to "GET".
        repeat_codes: The HTTP status codes indicating a redirect where
            the method cannot change and future requests should be repeated.
    '''
    REDIRECT_CODES = (301, 302, 303)
    REPEAT_REDIRECT_CODES = (307, 308)

    def __init__(self, max_redirects=20, codes=REDIRECT_CODES,
    repeat_codes=REPEAT_REDIRECT_CODES):
        self._max_redirects = max_redirects
        self._codes = codes
        self._repeat_codes = repeat_codes
        self._response = None
        self._num_redirects = 0

    def load(self, response):
        '''Load the response and increment the counter.

        Args:
            response (Response): An instance of :class:`Response`.
        '''
        self._response = response

        if self.next_location(raw=True):
            self._num_redirects += 1

    def next_location(self, raw=False):
        '''Returns the next location.

        Args:
            raw (bool): If True, the original string contained in the Location
                field will be returned. Otherwise, the URL will be
                normalized to a complete URL.

        Returns:
            str, None: If str, the location. Otherwise, no next location.
        '''
        if self._response:
            location = self._response.fields.get('location')

            if not location or raw:
                return location

            return wpull.url.urljoin(self._response.url_info.url, location)

    def is_redirect(self):
        '''Return whether the response contains a redirect code.'''
        if self._response:
            status_code = self._response.status_code
            return status_code in self._codes \
                or status_code in self._repeat_codes

    def is_repeat(self):
        '''Return whether the next request should be repeated.'''
        if self._response:
            return self._response.status_code in self._repeat_codes

    def count(self):
        '''Return the number of redirects received so far.'''
        return self._num_redirects

    def exceeded(self):
        '''Return whether the number of redirects has exceeded the maximum.'''
        return self._num_redirects > self._max_redirects


class RichClientResponseType(object):
    '''Indicates the type of response.'''
    normal = 1
    '''Normal response.'''
    redirect = 2
    '''Redirect.'''
    robots = 3
    '''Response to a robots.txt request.'''


class RichClient(BaseClient):
    '''HTTP client with redirect, cookies, and robots.txt handling.

    Args:
        http_client (Client): An instance of `Client`.
        robots_txt_pool (RobotsTxtPool): If provided an instance of
            :class:`.robots.RobotsTxtPool`, robots.txt handling is enabled.
        request_factory: A callable object that creates a :class:`Request`
            via :func:`Request.new`.
            This factory is used for redirects and robots.txt handling.
        redirect_tracker_factory: A callable object that creates a
            :class:`RedirectTracker`.
        cookie_jar (CookieJar): An instance of
            :class:`.wrapper.CookieJarWrapper`.
    '''
    def __init__(self, http_client, robots_txt_pool=None,
    request_factory=Request.new, redirect_tracker_factory=RedirectTracker,
    cookie_jar=None):
        super().__init__()
        self._http_client = http_client
        self._robots_txt_pool = robots_txt_pool
        self._request_factory = request_factory
        self._redirect_tracker_factory = redirect_tracker_factory
        self._cookie_jar = cookie_jar

    @property
    def robots_txt_pool(self):
        '''Return RobotsTxtPool.'''
        return self._robots_txt_pool

    @property
    def redirect_tracker_factory(self):
        '''Return the Redirect Tracker factory.'''
        return self._redirect_tracker_factory

    @property
    def request_factory(self):
        '''Return the Request factory.'''
        return self._request_factory

    @property
    def cookie_jar(self):
        '''Return the Cookie Jar.'''
        return self._cookie_jar

    @property
    def http_client(self):
        '''Return the HTTP Client.'''
        return self._http_client

    @property
    def _session_class(self):
        '''Return the Rich Client Session factory.'''
        if self._robots_txt_pool:
            return RobotsTxtRichClientSession
        else:
            return RichClientSession

    def session(self, request):
        '''Return a fetch session.

        Args:
            request (Request): An instance of :class:`Request`.

        Example usage::

            client = RichClient(Client())
            session = client.fetch(Request.new('http://www.example.com'))

            while not session.done:
                response = yield session.fetch()

            print(response)

        Returns:
            RichClientSession: An instance of :class:`RichClientSession`.
        '''
        return self._session_class(self, request)

    def close(self):
        '''Close the client and connections.'''
        self._http_client.close()

        if self._cookie_jar:
            self._cookie_jar.close()


class RichClientSession(object):
    '''A Rich Client Session.'''
    def __init__(self, rich_client, request):
        super().__init__()
        self._rich_client = rich_client
        self._original_request = request
        self._next_request = request
        self._redirect_tracker = rich_client.redirect_tracker_factory()
        self._response_type = None

        if rich_client.cookie_jar:
            self._add_cookies(request)

    @property
    def redirect_tracker(self):
        '''Return the Redirect Tracker.'''
        return self._redirect_tracker

    @property
    def next_request(self):
        '''Return the next Request to be fetched.'''
        return self._next_request

    @property
    def done(self):
        '''Return whether the session has finished.

        Returns:
            bool: If True, the document has been fully fetched.'''
        return self.next_request is None

    @property
    def response_type(self):
        '''Return the type of response.

        :seealso: :class:`RichClientResponseType`.
        '''
        return self._response_type

    @tornado.gen.coroutine
    def fetch(self, **kwargs):
        '''Fetch the request.

        Args:
            kwargs: Extra arguments passed to :func:`Client.fetch`.

        Returns:
            Response: An instance of :class:`Response`.
        '''
        request = self.next_request
        assert request
        response = yield self._rich_client.http_client.fetch(
            request, **kwargs)

        self._handle_response(response)

        raise tornado.gen.Return(response)

    def _handle_response(self, response):
        '''Handle the response and update the internal state.'''
        _logger.debug('Handling response')
        self._redirect_tracker.load(response)

        if self._rich_client.cookie_jar:
            self._extract_cookies(response)

        if self._redirect_tracker.is_redirect():
            self._update_redirect_request()
            self._response_type = RichClientResponseType.redirect
        else:
            self._next_request = None
            self._response_type = RichClientResponseType.normal

        if self._rich_client.cookie_jar and self._next_request:
            self._add_cookies(self._next_request)

    def _update_redirect_request(self):
        '''Update the Redirect Tracker.'''
        _logger.debug('Handling redirect.')

        if self._redirect_tracker.exceeded():
            raise ProtocolError('Too many redirects.')

        url = self._redirect_tracker.next_location()

        if not url:
            raise ProtocolError('Redirect location missing.')

        request = self._rich_client.request_factory(url)

        if self._redirect_tracker.is_repeat():
            _logger.debug('Got redirect is repeat.')

            request.method = self._original_request.method
            request.body = self._original_request.body

            for name, value in self._original_request.fields.items():
                if name not in request.fields:
                    request.fields.add(name, value)

        self._next_request = request

        _logger.debug('Updated next redirect request to {0}.'.format(request))

    def _get_cookie_referrer_host(self):
        '''Return the referrer hostname.'''
        referer = self._original_request.fields.get('Referer')

        if referer:
            return URLInfo.parse(referer).hostname
        else:
            return None

    def _add_cookies(self, request):
        '''Add the cookie headers to the Request.'''
        self._rich_client.cookie_jar.add_cookie_header(
            request, self._get_cookie_referrer_host()
        )

    def _extract_cookies(self, response):
        '''Load the cookie headers from the Response.'''
        self._rich_client.cookie_jar.extract_cookies(
            response, self._next_request, self._get_cookie_referrer_host()
        )


class RobotsTxtRichClientSession(RichClientSession):
    '''Rich Client Session with robots.txt handling.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._robots_txt_pool = self._rich_client.robots_txt_pool
        self._robots_attempts_remaining = 20
        self._robots_redirect_tracker = \
            self._rich_client.redirect_tracker_factory()
        self._robots_redirect_url = None
        self._robots_state = RobotsState.unknown
        self._robots_request = None

    @property
    def next_request(self):
        if self._robots_state == RobotsState.unknown:
            self._check_robots_pool()

        if self._robots_state == RobotsState.ok:
            return super().next_request
        elif self._robots_state == RobotsState.denied:
            return None
        else:
            return self._next_robots_request()

    def _next_robots_request(self):
        if self._robots_redirect_url:
            request = self._rich_client.request_factory(
                self._robots_redirect_url, url_encoding='latin-1'
            )

            self._robots_redirect_url = None
        else:
            url_info = super().next_request.url_info
            url = URLInfo.parse('{0}://{1}:{2}/robots.txt'.format(
                url_info.scheme, url_info.hostname, url_info.port)).url
            request = self._rich_client.request_factory(
                url, url_encoding=url_info.encoding
            )

        self._robots_request = request

        return request

    @tornado.gen.coroutine
    def fetch(self, **kwargs):
        if self._robots_state == RobotsState.unknown:
            self._check_robots_pool()

        if self._robots_state == RobotsState.denied:
            raise RobotsDenied(
                'Unable to fetch {url} due to robots.txt'.format(
                    url=self._original_request.url_info.url)
            )

        if self._robots_state in (RobotsState.ok, RobotsState.error):
            raise tornado.gen.Return((yield super().fetch(**kwargs)))

        request = self._next_robots_request()
        response = yield self._rich_client.http_client.fetch(request)

        self._handle_robots_response(response)

        raise tornado.gen.Return(response)

    def _check_robots_pool(self):
        url_info = super().next_request.url_info
        user_agent = super().next_request.fields.get('User-agent', '')

        if self._robots_txt_pool.has_parser(url_info):
            if self._robots_txt_pool.can_fetch(url_info, user_agent):
                self._robots_state = RobotsState.ok
            else:
                self._robots_state = RobotsState.denied
        else:
            self._robots_state = RobotsState.in_progress

    def _handle_robots_response(self, response):
        _logger.debug('Handling robots.txt response.')
        self._robots_redirect_tracker.load(response)

        self._response_type = RichClientResponseType.robots

        if self._robots_attempts_remaining == 0:
            _logger.warning(_('Too many failed attempts to get robots.txt.'))

            self._robots_state = RobotsState.error

        elif self._robots_redirect_tracker.exceeded():
            _logger.warning(_('Ignoring robots.txt redirect loop.'))

            self._robots_state = RobotsState.error

        elif not response or 500 <= response.status_code <= 599:
            _logger.debug('Temporary error getting robots.txt.')

            self._robots_attempts_remaining -= 1

        elif self._robots_redirect_tracker.is_redirect():
            _logger.debug('Got a redirect for robots.txt.')
            self._accept_empty(self._robots_request.url_info)

            self._robots_redirect_url = \
                self._robots_redirect_tracker.next_location()
        else:
            if response.status_code == 200:
                self._accept_ok(response)
            else:
                self._accept_empty(self._robots_request.url_info)

            self._check_robots_pool()

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
