'''FTP'''
import asyncio
import copy
import fnmatch
import gettext
import logging
import os
import posixpath
import tempfile
import urllib.parse

import namedlist
from typing import cast

from wpull.backport.logging import StyleAdapter
from wpull.body import Body
from wpull.cache import LRUCache
from wpull.errors import ProtocolError
from wpull.application.hook import Actions
from wpull.pipeline.item import LinkType
from wpull.pipeline.session import ItemSession
from wpull.processor.base import BaseProcessor, BaseProcessorSession, \
    REMOTE_ERRORS
from wpull.processor.rule import ResultRule, FetchRule
from wpull.protocol.ftp.client import Client
from wpull.protocol.ftp.request import Request, ListingResponse, Response
from wpull.protocol.ftp.util import FTPServerError
from wpull.scraper.util import urljoin_safe
from wpull.url import parse_url_or_log, URLInfo
from wpull.writer import NullWriter, BaseFileWriter

_logger = StyleAdapter(logging.getLogger(__name__))
_ = gettext.gettext

GLOB_CHARS = frozenset('[]*?')


FTPProcessorFetchParams = namedlist.namedtuple(
    'FTPProcessorFetchParamsType',
    [
        ('remove_listing', True),
        ('glob', True),
        ('preserve_permissions', False),
        ('retr_symlinks', True),
    ]
)
'''FTPProcessorFetchParams

Args:
    remove_listing (bool): Remove `.listing` files after fetching.
    glob (bool): Enable URL globbing.
    preserve_permissions (bool): Preserve file permissions.
    follow_symlinks (bool): Follow symlinks.
'''


class HookPreResponseBreak(ProtocolError):
    '''Hook pre-response break.'''


class FTPProcessor(BaseProcessor):
    '''FTP processor.

    Args:
        ftp_client: The FTP client.
        fetch_params (:class:`WebProcessorFetchParams`): Parameters for
            fetching.
    '''
    def __init__(self, ftp_client: Client, fetch_params):
        super().__init__()

        self._ftp_client = ftp_client
        self._fetch_params = fetch_params
        self._listing_cache = LRUCache(max_items=10, time_to_live=3600)

    @property
    def ftp_client(self) -> Client:
        '''The ftp client.'''
        return self._ftp_client

    @property
    def fetch_params(self) -> FTPProcessorFetchParams:
        '''The fetch parameters.'''
        return self._fetch_params

    @property
    def listing_cache(self) -> LRUCache:
        '''Listing cache.

        Returns:
            A cache mapping
            from URL to list of :class:`.ftp.ls.listing.FileEntry`.
        '''
        return self._listing_cache

    @asyncio.coroutine
    def process(self, item_session: ItemSession):
        session = FTPProcessorSession(self, item_session)
        try:
            return (yield from session.process())
        finally:
            session.close()

    def close(self):
        '''Close the FTP client.'''
        self._ftp_client.close()


class FTPProcessorSession(BaseProcessorSession):
    '''Fetches FTP files or directory listings.'''
    def __init__(self, processor: FTPProcessor, item_session: ItemSession):
        super().__init__()
        self._processor = processor
        self._item_session = item_session
        self._fetch_rule = cast(FetchRule, item_session.app_session.factory['FetchRule'])
        self._result_rule = cast(ResultRule, item_session.app_session.factory['ResultRule'])

        file_writer = cast(BaseFileWriter, item_session.app_session.factory['FileWriter'])

        self._file_writer_session = file_writer.session()
        self._glob_pattern = None

    def close(self):
        pass

    @asyncio.coroutine
    def process(self):
        '''Process.

        Coroutine.
        '''
        self._item_session.request = request = Request(self._item_session.url_record.url)
        verdict = self._fetch_rule.check_ftp_request(self._item_session)[0]

        if not verdict:
            self._item_session.skip()
            return

        self._add_request_password(request)

        dir_name, filename = self._item_session.url_record.url_info.split_path()
        if self._processor.fetch_params.glob and frozenset(filename) & GLOB_CHARS:
            request = self._to_directory_request(request)
            is_file = False
            self._glob_pattern = urllib.parse.unquote(filename)
        else:
            is_file = yield from self._prepare_request_file_vs_dir(request)

            self._file_writer_session.process_request(request)

        wait_time = yield from self._fetch(request, is_file)

        if wait_time:
            _logger.debug('Sleeping {0}.', wait_time)
            yield from asyncio.sleep(wait_time)

    def _add_request_password(self, request: Request):
        if self._fetch_rule.ftp_login:
            request.username, request.password = self._fetch_rule.ftp_login

    @classmethod
    def _to_directory_request(cls, request: Request) -> Request:
        directory_url = to_dir_path_url(request.url_info)
        directory_request = copy.deepcopy(request)
        directory_request.url = directory_url

        return directory_request

    @asyncio.coroutine
    def _prepare_request_file_vs_dir(self, request: Request) -> bool:
        '''Check if file, modify request, and return whether is a file.

        Coroutine.
        '''
        if self._item_session.url_record.link_type:
            is_file = self._item_session.url_record.link_type == LinkType.file
        elif request.url_info.path.endswith('/'):
            is_file = False
        else:
            is_file = 'unknown'

        if is_file == 'unknown':
            files = yield from self._fetch_parent_path(request)

            if not files:
                return True

            filename = posixpath.basename(request.file_path)

            for file_entry in files:
                if file_entry.name == filename:
                    _logger.debug('Found entry in parent. Type {}',
                                  file_entry.type)
                    is_file = file_entry.type != 'dir'
                    break
            else:
                _logger.debug('Did not find entry. Assume file.')
                return True

            if not is_file:
                request.url = append_slash_to_path_url(request.url_info)
                _logger.debug('Request URL changed to {}. Path={}.',
                              request.url, request.file_path)

        return is_file

    @asyncio.coroutine
    def _fetch_parent_path(self, request: Request, use_cache: bool=True):
        '''Fetch parent directory and return list FileEntry.

        Coroutine.
        '''
        directory_url = to_dir_path_url(request.url_info)

        if use_cache:
            if directory_url in self._processor.listing_cache:
                return self._processor.listing_cache[directory_url]

        directory_request = copy.deepcopy(request)
        directory_request.url = directory_url

        _logger.debug('Check if URL {} is file with {}.', request.url,
                      directory_url)

        with self._processor.ftp_client.session() as session:
            try:
                yield from session.start_listing(directory_request)
            except FTPServerError:
                _logger.debug('Got an error. Assume is file.')

                if use_cache:
                    self._processor.listing_cache[directory_url] = None

                return

            temp_file = tempfile.NamedTemporaryFile(
                dir=self._item_session.app_session.root_path,
                prefix='tmp-wpull-list'
            )

            with temp_file as file:
                directory_response = yield from session.download_listing(
                    file, duration_timeout=self._fetch_rule.duration_timeout)

        if use_cache:
            self._processor.listing_cache[directory_url] = \
                directory_response.files

        return directory_response.files

    @asyncio.coroutine
    def _fetch(self, request: Request, is_file: bool):
        '''Fetch the request

        Coroutine.
        '''
        _logger.info(_('Fetching ‘{url}’.'), url=request.url)

        self._item_session.request = request
        response = None

        try:
            with self._processor.ftp_client.session() as session:
                if is_file:
                    response = yield from session.start(request)
                else:
                    response = yield from session.start_listing(request)

                self._item_session.response = response

                action = self._result_rule.handle_pre_response(
                    self._item_session
                )

                if action in (Actions.RETRY, Actions.FINISH):
                    raise HookPreResponseBreak()

                self._file_writer_session.process_response(response)

                if not response.body:
                    response.body = Body(
                        directory=self._item_session.app_session.root_path,
                        hint='resp_cb')

                duration_timeout = self._fetch_rule.duration_timeout

                if is_file:
                    yield from session.download(
                        response.body, duration_timeout=duration_timeout)
                else:
                    yield from session.download_listing(
                        response.body, duration_timeout=duration_timeout)

        except HookPreResponseBreak:
            if response:
                response.body.close()

        except REMOTE_ERRORS as error:
            self._log_error(request, error)

            self._result_rule.handle_error(self._item_session, error)

            wait_time = self._result_rule.get_wait_time(
                self._item_session, error=error
            )

            if response:
                response.body.close()

            return wait_time
        else:
            self._log_response(request, response)
            self._handle_response(request, response)

            wait_time = self._result_rule.get_wait_time(
                self._item_session
            )

            if is_file and \
                    self._processor.fetch_params.preserve_permissions and \
                    hasattr(response.body, 'name'):
                yield from self._apply_unix_permissions(request, response)

            response.body.close()

            return wait_time

    def _add_listing_links(self, response: ListingResponse):
        '''Add links from file listing response.'''
        base_url = response.request.url_info.url

        if self._glob_pattern:
            level = self._item_session.url_record.level
        else:
            level = None

        for file_entry in response.files:
            if self._glob_pattern and \
                    not fnmatch.fnmatchcase(file_entry.name, self._glob_pattern):
                continue

            if file_entry.type == 'dir':
                linked_url = urljoin_safe(base_url, file_entry.name + '/')
            elif file_entry.type in ('file', 'symlink', None):
                if not self._processor.fetch_params.retr_symlinks and \
                        file_entry.type == 'symlink':
                    self._make_symlink(file_entry.name, file_entry.dest)
                    linked_url = None
                else:
                    linked_url = urljoin_safe(base_url, file_entry.name)
            else:
                linked_url = None

            if linked_url:
                linked_url_info = parse_url_or_log(linked_url)

                if linked_url_info:
                    verdict = self._fetch_rule.check_ftp_request(self._item_session)[0]

                    if verdict:
                        if linked_url_info.path.endswith('/'):
                            self._item_session.add_child_url(linked_url_info.url, link_type=LinkType.directory)
                        else:
                            self._item_session.add_child_url(linked_url_info.url, link_type=LinkType.file, level=level)

    def _log_response(self, request: Request, response: Response):
        '''Log response.'''
        _logger.info(
            _('Fetched ‘{url}’: {reply_code} {reply_text}. '
                'Length: {content_length}.'),
            url=request.url,
            reply_code=response.reply.code,
            reply_text=response.reply.text,
            content_length=response.body.size(),
        )

    def _handle_response(self, request: Request, response: Response):
        '''Process a response.'''
        self._item_session.update_record_value(status_code=response.reply.code)
        is_listing = isinstance(response, ListingResponse)

        if is_listing and not self._processor.fetch_params.remove_listing or \
                not is_listing:
            filename = self._file_writer_session.save_document(response)
            action = self._result_rule.handle_document(self._item_session, filename)
        else:
            self._file_writer_session.discard_document(response)
            action = self._result_rule.handle_no_document(self._item_session)

        if isinstance(response, ListingResponse):
            self._add_listing_links(response)

        return action

    def _make_symlink(self, link_name: str, link_target: str):
        '''Make a symlink on the system.'''
        path = self._file_writer_session.extra_resource_path('dummy')

        if path:
            dir_path = os.path.dirname(path)
            symlink_path = os.path.join(dir_path, link_name)

            _logger.debug('symlink {} -> {}', symlink_path, link_target)

            os.symlink(link_target, symlink_path)

            _logger.info(
                _('Created symbolic link {symlink_path} to target {symlink_target}.'),
                symlink_path=symlink_path,
                symlink_target=link_target
            )

    @asyncio.coroutine
    def _apply_unix_permissions(self, request: Request, response: Response):
        '''Fetch and apply Unix permissions.

        Coroutine.
        '''
        files = yield from self._fetch_parent_path(request)

        if not files:
            return

        filename = posixpath.basename(request.file_path)

        for file_entry in files:
            if file_entry.name == filename and file_entry.perm:
                _logger.debug(
                    'Set chmod {} o{:o}.',
                    response.body.name, file_entry.perm
                )
                os.chmod(response.body.name, file_entry.perm)


def to_dir_path_url(url_info: URLInfo) -> str:
    '''Return URL string with the path replaced with directory only.'''
    dir_name = posixpath.dirname(url_info.path)

    if not dir_name.endswith('/'):
        url_template = 'ftp://{}{}/'
    else:
        url_template = 'ftp://{}{}'

    return url_template.format(url_info.hostname_with_port, dir_name)


def append_slash_to_path_url(url_info: URLInfo) -> str:
    '''Return URL string with the path suffixed with a slash.'''
    return 'ftp://{}{}/'.format(url_info.hostname_with_port, url_info.path)
