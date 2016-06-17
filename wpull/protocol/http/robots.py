# encoding=utf-8
'''Robots.txt file logistics.'''
import contextlib
import gettext
import logging
import os

import asyncio

from wpull.backport.logging import BraceMessage as __
import wpull.body
from wpull.errors import ServerError, ProtocolError
from wpull.protocol.http.request import Request, Response
from wpull.protocol.http.web import WebClient
from wpull.robotstxt import RobotsTxtPool
from wpull.url import URLInfo
import wpull.util


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class NotInPoolError(Exception):
    '''The URL is not in the pool.'''
    pass


class RobotsTxtChecker(object):
    '''Robots.txt file fetcher and checker.

    args:
        web_client: Web Client.
        robots_txt_pool: Robots.txt Pool.
    '''
    def __init__(self, web_client: WebClient=None, robots_txt_pool: RobotsTxtPool=None):
        self._web_client = web_client or WebClient()
        self._robots_txt_pool = robots_txt_pool or RobotsTxtPool()

    @property
    def web_client(self) -> WebClient:
        '''Return the WebClient.'''
        return self._web_client

    @property
    def robots_txt_pool(self) -> RobotsTxtPool:
        '''Return the RobotsTxtPool.'''
        return self._robots_txt_pool

    def can_fetch_pool(self, request: Request):
        '''Return whether the request can be fetched based on the pool.'''
        url_info = request.url_info
        user_agent = request.fields.get('User-agent', '')

        if self._robots_txt_pool.has_parser(url_info):
            return self._robots_txt_pool.can_fetch(url_info, user_agent)
        else:
            raise NotInPoolError()

    @asyncio.coroutine
    def fetch_robots_txt(self, request: Request, file=None):
        '''Fetch the robots.txt file for the request.

        Coroutine.
        '''
        url_info = request.url_info
        url = URLInfo.parse('{0}://{1}/robots.txt'.format(
            url_info.scheme, url_info.hostname_with_port)).url

        if not file:
            file = wpull.body.new_temp_file(os.getcwd(), hint='robots')

        with contextlib.closing(file):
            request = Request(url)

            session = self._web_client.session(request)
            while not session.done():
                wpull.util.truncate_file(file.name)

                try:
                    response = yield from session.start()
                    yield from session.download(file=file)
                except ProtocolError:
                    self._accept_as_blank(url_info)

                    return

            status_code = response.status_code

            if 500 <= status_code <= 599:
                raise ServerError('Server returned error for robots.txt.')

            if status_code == 200:
                self._read_content(response, url_info)
            else:
                self._accept_as_blank(url_info)

    @asyncio.coroutine
    def can_fetch(self, request: Request, file=None) -> bool:
        '''Return whether the request can fetched.

        Args:
            request: Request.
            file: A file object to where the robots.txt contents are written.

        Coroutine.
        '''
        try:
            return self.can_fetch_pool(request)
        except NotInPoolError:
            pass

        yield from self.fetch_robots_txt(request, file=file)

        return self.can_fetch_pool(request)

    def _read_content(self, response: Response, original_url_info: URLInfo):
        '''Read response and parse the contents into the pool.'''
        data = response.body.read(4096)
        url_info = original_url_info

        try:
            self._robots_txt_pool.load_robots_txt(url_info, data)
        except ValueError:
            _logger.warning(__(
                _('Failed to parse {url} for robots exclusion rules. '
                  'Ignoring.'), url_info.url))
            self._accept_as_blank(url_info)
        else:
            _logger.debug(__('Got a good robots.txt for {0}.',
                             url_info.url))

    def _accept_as_blank(self, url_info: URLInfo):
        '''Mark the URL as OK in the pool.'''
        _logger.debug(__('Got empty robots.txt for {0}.', url_info.url))
        self._robots_txt_pool.load_robots_txt(url_info, '')
