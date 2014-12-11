# encoding=utf-8
'''Advanced HTTP Client handling.'''
import base64
import gettext
import logging
import http.client

from trollius import From, Return
import trollius

from wpull.errors import ProtocolError
from wpull.http.client import Client
from wpull.http.redirect import RedirectTracker
from wpull.http.request import Request
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
    authentication = 4
    '''Response to a HTTP authentication.'''


class WebClient(object):
    '''A web client handles redirects and cookies.

    Args:
        http_client (:class:`.http.client.Client`). An HTTP client.
        requets_factory: A function that returns a new
            :class:`.http.request.Request`
        redirect_tracker_factory: A function that returns a new
            :class:`.http.redirect.RedirectTracker`
        cookie_jar (:class:`.wrapper.CookieJarWrapper`): A cookie jar.
    '''
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
            request (:class:`.http.request.Request`): The request to be
                fetched.

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

    def close(self):
        self._http_client.close()

        if self._cookie_jar:
            self._cookie_jar.close()


class WebSession(object):
    '''A web session.'''
    def __init__(self, web_client, request):
        self._web_client = web_client
        self._original_request = request
        self._next_request = request
        self._redirect_tracker = web_client.redirect_tracker_factory()
        self._loop_type = LoopType.normal
        self._hostnames_with_auth = set()

        if self._web_client.cookie_jar:
            self._add_cookies(self._next_request)

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
        '''Fetch one of the requests.

        Args:
            file: An optional file object for the document contents.
            callback: A callback function for the document contents.
                The callback is given 2 arguments: request and response.
                The callback returns a file object or None.

        Returns:
            Response: An instance of :class:`.http.request.Response`.

        See :meth:`WebClient.session` for proper usage of this function.

        Coroutine.
        '''
        with self._web_client.http_client.session() as session:
            request = self.next_request()
            assert request

            if request.url_info.password or \
                    request.url_info.hostname_with_port in self._hostnames_with_auth:
                self._add_basic_auth_header(request)

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
        elif response.status_code == http.client.UNAUTHORIZED and self._next_request.password:
            self._process_authentication(response)
        else:
            self._next_request = None
            self._loop_type = LoopType.normal

        if self._web_client.cookie_jar:
            self._extract_cookies(response)

            if self._web_client.cookie_jar and self._next_request:
                self._add_cookies(self._next_request)

    def _process_redirect(self):
        '''Update the Redirect Tracker.'''
        _logger.debug('Handling redirect.')

        if self._redirect_tracker.exceeded():
            raise ProtocolError('Too many redirects.')

        try:
            url = self._redirect_tracker.next_location()

            if not url:
                raise ProtocolError('Redirect location missing.')

            if self._redirect_tracker.is_repeat():
                _logger.debug('Got redirect is repeat.')

                request = self._original_request.copy()
                request.url = url
            else:
                request = self._web_client.request_factory(url)

            request.prepare_for_send()
        except ValueError as error:
            raise ProtocolError('Invalid redirect location.') from error

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
            response, response.request, self._get_cookie_referrer_host()
        )

    def _process_authentication(self, response):
        if self._loop_type == LoopType.authentication:
            _logger.warning(_('Unable to authenticate.'))
            self._next_request = None
            self._loop_type = LoopType.normal
            return

        self._add_basic_auth_header(self._next_request)
        self._loop_type = LoopType.authentication
        self._hostnames_with_auth.add(self._next_request.url_info.hostname_with_port)

    def _add_basic_auth_header(self, request):
        username = request.url_info.username or request.username
        password = request.url_info.password or request.password

        if username and password:
            _logger.debug('Add basic auth header')

            auth_string = '{}:{}'.format(username, password)
            auth_string = base64.b64encode(
                auth_string.encode('utf-8', 'replace')).decode('utf-8')
            request.fields['Authorization'] = 'Basic {}'.format(auth_string)

