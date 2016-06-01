# encoding=utf-8
'''Advanced HTTP Client handling.'''
import base64
import enum
import gettext
import logging
import http.client

import asyncio

from typing import Optional, Callable, IO
from wpull.errors import ProtocolError
from wpull.protocol.http.client import Client
from wpull.protocol.http.redirect import RedirectTracker
from wpull.protocol.http.request import Request, Response
from wpull.url import URLInfo
from wpull.cookiewrapper import CookieJarWrapper

_ = gettext.gettext
_logger = logging.getLogger(__name__)


class LoopType(enum.Enum):
    '''Indicates the type of request and response.'''
    normal = 1
    '''Normal response.'''
    redirect = 2
    '''Redirect.'''
    robots = 3
    '''Response to a robots.txt request.'''
    authentication = 4
    '''Response to a HTTP authentication.'''


class WebSession(object):
    '''A web session.'''
    def __init__(self, request: Request,
                 http_client: Client,
                 redirect_tracker: RedirectTracker,
                 request_factory: Callable[..., Request],
                 cookie_jar: Optional[CookieJarWrapper]=None):
        self._original_request = request
        self._next_request = request
        self._http_client = http_client
        self._redirect_tracker = redirect_tracker
        self._request_factory = request_factory
        self._cookie_jar = cookie_jar

        self._loop_type = LoopType.normal
        self._hostnames_with_auth = set()
        self._current_session = None

        if self._cookie_jar:
            self._add_cookies(self._next_request)

    @property
    def redirect_tracker(self) -> RedirectTracker:
        '''Return the Redirect Tracker.'''
        return self._redirect_tracker

    def next_request(self) -> Optional[Request]:
        '''Return the next Request to be fetched.'''
        return self._next_request

    def done(self) -> bool:
        '''Return whether the session has finished.

        Returns:
            bool: If True, the document has been fully fetched.'''
        return self.next_request() is None

    def loop_type(self) -> LoopType:
        '''Return the type of response.

        :seealso: :class:`LoopType`.
        '''
        return self._loop_type

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._current_session:
            if not isinstance(exc_val, StopIteration):
                self._current_session.abort()
            self._current_session.recycle()

    @asyncio.coroutine
    def start(self):
        '''Begin fetching the next request.'''
        self._current_session = session = self._http_client.session()

        request = self.next_request()
        assert request

        if request.url_info.password or \
                request.url_info.hostname_with_port in self._hostnames_with_auth:
            self._add_basic_auth_header(request)

        response = yield from session.start(request)

        self._process_response(response)

        return response

    @asyncio.coroutine
    def download(self, file: Optional[IO[bytes]]=None,
                 duration_timeout: Optional[float]=None):
        '''Download content.

        Args:
            file: An optional file object for the document contents.
            duration_timeout: Maximum time in seconds of which the
                entire file must be read.

        Returns:
            Response: An instance of :class:`.http.request.Response`.

        See :meth:`WebClient.session` for proper usage of this function.

        Coroutine.
        '''
        yield from \
            self._current_session.download(file, duration_timeout=duration_timeout)

        self._current_session = None

    def _process_response(self, response: Response):
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

        if self._cookie_jar:
            self._extract_cookies(response)

            if self._next_request:
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
                request = self._request_factory(url)

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

    def _add_cookies(self, request: Request):
        '''Add the cookie headers to the Request.'''
        self._cookie_jar.add_cookie_header(
            request, self._get_cookie_referrer_host()
        )

    def _extract_cookies(self, response: Response):
        '''Load the cookie headers from the Response.'''
        self._cookie_jar.extract_cookies(
            response, response.request, self._get_cookie_referrer_host()
        )

    def _process_authentication(self, response: Response):
        if self._loop_type == LoopType.authentication:
            _logger.warning(_('Unable to authenticate.'))
            self._next_request = None
            self._loop_type = LoopType.normal
            return

        self._add_basic_auth_header(self._next_request)
        self._loop_type = LoopType.authentication
        self._hostnames_with_auth.add(self._next_request.url_info.hostname_with_port)

    def _add_basic_auth_header(self, request: Request):
        username = request.url_info.username or request.username
        password = request.url_info.password or request.password

        if username and password:
            _logger.debug('Add basic auth header')

            auth_string = '{}:{}'.format(username, password)
            auth_string = base64.b64encode(
                auth_string.encode('utf-8', 'replace')).decode('utf-8')
            request.fields['Authorization'] = 'Basic {}'.format(auth_string)


class WebClient(object):
    '''A web client handles redirects, cookies, basic authentication.

    Args:
        http_client. An HTTP client.
        requets_factory: A function that returns a new
            :class:`.http.request.Request`
        redirect_tracker_factory: A function that returns a new
            :class:`.http.redirect.RedirectTracker`
        cookie_jar: A cookie jar.
    '''
    def __init__(self, http_client: Optional[Client]=None,
                 request_factory: Callable[..., Request]=Request,
                 redirect_tracker_factory:
                 Optional[Callable[..., RedirectTracker]]=RedirectTracker,
                 cookie_jar: Optional[CookieJarWrapper]=None):
        super().__init__()
        self._http_client = http_client or Client()
        self._request_factory = request_factory
        self._redirect_tracker_factory = redirect_tracker_factory
        self._cookie_jar = cookie_jar
        self._loop_type = None

    @property
    def redirect_tracker_factory(self) -> Callable[..., RedirectTracker]:
        '''Return the Redirect Tracker factory.'''
        return self._redirect_tracker_factory

    @property
    def request_factory(self) -> Callable[..., Request]:
        '''Return the Request factory.'''
        return self._request_factory

    @property
    def cookie_jar(self) -> CookieJarWrapper:
        '''Return the Cookie Jar.'''
        return self._cookie_jar

    @property
    def http_client(self) -> Client:
        '''Return the HTTP Client.'''
        return self._http_client

    def session(self, request: Request) -> WebSession:
        '''Return a fetch session.

        Args:
            request: The request to be fetched.

        Example usage::

            client = WebClient()
            session = client.session(Request('http://www.example.com'))

            with session:
                while not session.done():
                    request = session.next_request()
                    print(request)

                    response = yield from session.start()
                    print(response)

                    if session.done():
                        with open('myfile.html') as file:
                            yield from session.download(file)
                    else:
                        yield from session.download()

        Returns:
            WebSession
        '''
        return WebSession(
            request,
            http_client=self._http_client,
            redirect_tracker=self._redirect_tracker_factory(),
            request_factory=self._request_factory,
            cookie_jar=self._cookie_jar,
        )

    def close(self):
        self._http_client.close()

        if self._cookie_jar:
            self._cookie_jar.close()
