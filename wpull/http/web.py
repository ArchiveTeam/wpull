# encoding=utf-8
'''Advanced HTTP Client handling.'''
import gettext
import io
import logging

from trollius import From, Return
import trollius

from wpull.errors import ProtocolError
from wpull.http.client import Client
from wpull.http.redirect import RedirectTracker
from wpull.http.request import Request
from wpull.robotstxt import RobotsDenied
from wpull.url import URLInfo


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class LoopType(object):
    '''Indicates the type of request and response.'''
    normal = 1
    '''Normal response.'''
    redirect = 2
    '''Redirect.'''
    robots = 3
    '''Response to a robots.txt request.'''


class WebClient(object):
    def __init__(self, http_client=None, request_factory=Request,
                 redirect_tracker_factory=RedirectTracker,
                 cookie_jar=None):
        super().__init__()
        self._http_client = http_client or Client()
        self._request_factory = request_factory
        self._redirect_tracker_factory = redirect_tracker_factory
        self._cookie_jar = cookie_jar
        self._loop_type = None

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

    def session(self, request):
        '''Return a fetch session.

        Args:
            request (Request): An instance of :class:`Request`.

        Example usage::

            client = WebClient()
            session = client.fetch(Request('http://www.example.com'))

            while not session.done():
                response = yield from session.fetch()

            print(response)

        Returns:
            WebSession
        '''
        return WebSession(self, request)


class WebSession(object):
    def __init__(self, web_client, request):
        self._web_client = web_client
        self._original_request = request
        self._next_request = request
        self._redirect_tracker = web_client.redirect_tracker_factory()
        self._loop_type = LoopType.normal

    @property
    def redirect_tracker(self):
        '''Return the Redirect Tracker.'''
        return self._redirect_tracker

    def next_request(self):
        '''Return the next Request to be fetched.'''
        return self._next_request

    def done(self):
        '''Return whether the session has finished.

        Returns:
            bool: If True, the document has been fully fetched.'''
        return self.next_request() is None

    def loop_type(self):
        '''Return the type of response.

        :seealso: :class:`LoopType`.
        '''
        return self._loop_type

    @trollius.coroutine
    def fetch(self, file=None, callback=None):
        '''Fetch the request.

        Args:
            file: An optional file object for the document contents.
            callback: A callback function for the document contents.
                The callback is given 2 arguments: request and response.
                The callback returns a file object or None.

        Returns:
            Response: An instance of :class:`Response`.
        '''
        with self._web_client.http_client.session() as session:
            request = self.next_request()
            assert request
            response = yield From(session.fetch(request))

            if callback:
                file = callback(request, response)

            yield From(session.read_content(file))

        self._process_response(response)

        raise Return(response)

    def _process_response(self, response):
        '''Handle the response and update the internal state.'''
        _logger.debug('Handling response')

        self._redirect_tracker.load(response)

        if self._redirect_tracker.is_redirect():
            self._process_redirect()
            self._loop_type = LoopType.redirect
        else:
            self._next_request = None
            self._loop_type = LoopType.normal

        if self._web_client.cookie_jar:
            self._extract_cookies(response)

            if self._next_request:
                self._add_cookies(self._next_request)

    def _process_redirect(self):
        '''Update the Redirect Tracker.'''
        _logger.debug('Handling redirect.')

        if self._redirect_tracker.exceeded():
            raise ProtocolError('Too many redirects.')

        url = self._redirect_tracker.next_location()

        if not url:
            raise ProtocolError('Redirect location missing.')

        try:
            request = self._web_client.request_factory(url)
            request.prepare_for_send()
        except ValueError as error:
            raise ProtocolError('Invalid redirect location.') from error

        if self._redirect_tracker.is_repeat():
            _logger.debug('Got redirect is repeat.')

            request = self._original_request.copy()

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
        self._web_client.cookie_jar.add_cookie_header(
            request, self._get_cookie_referrer_host()
        )

    def _extract_cookies(self, response):
        '''Load the cookie headers from the Response.'''
        self._web_client.cookie_jar.extract_cookies(
            response, self._next_request, self._get_cookie_referrer_host()
        )


# TODO: rewrite this:
# class RobotsTxtRichClientSession(RichClientSession):
#     '''Rich Client Session with robots.txt handling.'''
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self._robots_txt_pool = self._rich_client.robots_txt_pool
#         self._robots_attempts_remaining = 20
#         self._robots_redirect_tracker = \
#             self._rich_client.redirect_tracker_factory()
#         self._robots_redirect_url = None
#         self._robots_state = RobotsState.unknown
#         self._robots_request = None
# 
#     @property
#     def next_request(self):
#         if self._robots_state != RobotsState.in_progress:
#             self._check_robots_pool()
# 
#         if self._robots_state == RobotsState.ok:
#             return super().next_request
#         elif self._robots_state == RobotsState.denied:
#             return None
#         else:
#             return self._next_robots_request()
# 
#     def _next_robots_request(self):
#         if self._robots_redirect_url:
#             request = self._rich_client.request_factory(
#                 self._robots_redirect_url, url_encoding='latin-1'
#             )
#         else:
#             url_info = super().next_request.url_info
#             url = URLInfo.parse('{0}://{1}:{2}/robots.txt'.format(
#                 url_info.scheme, url_info.hostname, url_info.port)).url
#             request = self._rich_client.request_factory(
#                 url, url_encoding=url_info.encoding
#             )
# 
#         self._robots_request = request
# 
#         return request
# 
#     @tornado.gen.coroutine
#     def fetch(self, **kwargs):
#         if self._robots_state != RobotsState.in_progress:
#             self._check_robots_pool()
# 
#         if self._robots_state == RobotsState.denied:
#             raise RobotsDenied(
#                 'Unable to fetch {url} due to robots.txt'.format(
#                     url=self._original_request.url_info.url)
#             )
# 
#         if self._robots_state in (RobotsState.ok, RobotsState.error):
#             raise tornado.gen.Return((yield super().fetch(**kwargs)))
# 
#         request = self._next_robots_request()
#         response = yield self._rich_client.http_client.fetch(request)
#         self._robots_redirect_url = None
# 
#         self._handle_robots_response(response)
# 
#         raise tornado.gen.Return(response)
# 
#     def _check_robots_pool(self):
#         if not super().next_request:
#             return
# 
#         url_info = super().next_request.url_info
#         user_agent = super().next_request.fields.get('User-agent', '')
# 
#         if self._robots_txt_pool.has_parser(url_info):
#             if self._robots_txt_pool.can_fetch(url_info, user_agent):
#                 self._robots_state = RobotsState.ok
#             else:
#                 self._robots_state = RobotsState.denied
#         else:
#             self._robots_state = RobotsState.in_progress
# 
#     def _handle_robots_response(self, response):
#         _logger.debug('Handling robots.txt response.')
#         self._robots_redirect_tracker.load(response)
# 
#         self._response_type = RichClientResponseType.robots
# 
#         if self._robots_attempts_remaining == 0:
#             _logger.warning(_('Too many failed attempts to get robots.txt.'))
# 
#             self._robots_txt_pool.load_robots_txt(
#                 self._robots_request.url_info,
#                 b'User-Agent: *\nDisallow: /\n'
#             )
#             self._check_robots_pool()
# 
#         elif self._robots_redirect_tracker.exceeded():
#             _logger.warning(_('Ignoring robots.txt redirect loop.'))
# 
#             self._accept_empty(self._robots_request.url_info)
#             self._check_robots_pool()
# 
#         elif not response or 500 <= response.status_code <= 599:
#             _logger.debug('Temporary error getting robots.txt.')
# 
#             self._robots_attempts_remaining -= 1
# 
#         elif self._robots_redirect_tracker.is_redirect():
#             _logger.debug('Got a redirect for robots.txt.')
#             self._accept_empty(self._robots_request.url_info)
# 
#             self._robots_redirect_url = \
#                 self._robots_redirect_tracker.next_location()
#         else:
#             if response.status_code == 200:
#                 self._accept_ok(response)
#             else:
#                 self._accept_empty(self._robots_request.url_info)
# 
#             self._check_robots_pool()
# 
#     def _accept_ok(self, response):
#         url_info = self._robots_request.url_info
# 
#         try:
#             self._robots_txt_pool.load_robots_txt(
#                 url_info,
#                 response.body.content_peek())
#         except ValueError:
#             _logger.warning(__(
#                 _('Failed to parse {url} for robots exclusion rules. '
#                     'Ignoring.'), url_info.url))
#             self._accept_empty(url_info)
#         else:
#             _logger.debug('Got a good robots.txt for {0}.'.format(
#                 url_info.url))
# 
#     def _accept_empty(self, url_info):
#         _logger.debug(__('Got empty robots.txt for {0}.', url_info.url))
#         self._robots_txt_pool.load_robots_txt(url_info, '')
