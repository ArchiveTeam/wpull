'''FTP'''
import copy
import gettext
import logging
import os
import posixpath
import tempfile

from trollius.coroutines import Return, From
import namedlist
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.cache import LRUCache
from wpull.errors import ProtocolError
from wpull.ftp.request import Request, ListingResponse
from wpull.ftp.util import FTPServerError
from wpull.hook import Actions
from wpull.item import LinkType
from wpull.processor.base import BaseProcessor, BaseProcessorSession, \
    REMOTE_ERRORS
from wpull.processor.rule import ResultRule, FetchRule
from wpull.scraper.util import urljoin_safe
from wpull.url import parse_url_or_log
from wpull.writer import NullWriter


_logger = logging.getLogger(__name__)
_ = gettext.gettext


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

FTPProcessorInstances = namedlist.namedtuple(
    'FTPProcessorInstancesType',
    [
        ('fetch_rule', FetchRule()),
        ('result_rule', ResultRule()),
        ('processing_rule', None),
        ('file_writer', NullWriter()),
    ]
)
'''FTPProcessorInstances

Args:
    fetch_rule ( :class:`.processor.rule.FetchRule`): The fetch rule.
    result_rule ( :class:`.processor.rule.ResultRule`): The result rule.
    processing_rule ( :class:`.processor.rule.ProcessingRule`): The processing rule.
    file_writer (:class`.writer.BaseWriter`): The file writer.
'''


class HookPreResponseBreak(ProtocolError):
    '''Hook pre-response break.'''


class FTPProcessor(BaseProcessor):
    '''FTP processor.

    Args:
        rich_client (:class:`.http.web.WebClient`): The web client.
        root_path (str): The root directory path.
        fetch_params (:class:`WebProcessorFetchParams`): Parameters for
            fetching.
        instances (:class:`WebProcessorInstances`): Instances needed
            by the processor.
    '''
    def __init__(self, ftp_client, root_path, fetch_params, instances):
        super().__init__()

        self._ftp_client = ftp_client
        self._root_path = root_path
        self._fetch_params = fetch_params
        self._instances = instances
        self._session_class = FTPProcessorSession
        self._listing_cache = LRUCache(max_items=10, time_to_live=3600)

    @property
    def ftp_client(self):
        '''The ftp client.'''
        return self._ftp_client

    @property
    def root_path(self):
        '''The root path.'''
        return self._root_path

    @property
    def instances(self):
        '''The processor instances.'''
        return self._instances

    @property
    def fetch_params(self):
        '''The fetch parameters.'''
        return self._fetch_params

    @property
    def listing_cache(self):
        '''Listing cache.

        Returns:
            :class:`.cache.LRUCache`: A cache mapping
            from URL to list of :class:`.ftp.ls.listing.FileEntry`.
        '''
        return self._listing_cache

    @trollius.coroutine
    def process(self, url_item):
        session = self._session_class(self, url_item)
        try:
            raise Return((yield From(session.process())))
        finally:
            session.close()

    def close(self):
        '''Close the FTP client.'''
        self._ftp_client.close()


class FTPProcessorSession(BaseProcessorSession):
    '''Fetches FTP files or directory listings.'''
    def __init__(self, processor, url_item):
        super().__init__()
        self._processor = processor
        self._url_item = url_item
        self._fetch_rule = processor.instances.fetch_rule
        self._result_rule = processor.instances.result_rule

        self._file_writer_session = processor.instances.file_writer.session()

    def close(self):
        pass

    @trollius.coroutine
    def process(self):
        '''Process.

        Coroutine.
        '''
        verdict = self._fetch_rule.check_ftp_request(
            self._url_item.url_info, self._url_item.url_record)[0]

        if not verdict:
            self._url_item.skip()
            return

        request = Request(self._url_item.url_info.url)  # TODO: dependency inject

        if self._fetch_rule.ftp_login:
            request.username, request.password = self._fetch_rule.ftp_login

        is_file = yield From(self._prepare_request_file_vs_dir(request))

        self._file_writer_session.process_request(request)

        wait_time = yield From(self._fetch(request, is_file))

        if wait_time:
            _logger.debug('Sleeping {0}.'.format(wait_time))
            yield From(trollius.sleep(wait_time))

    @trollius.coroutine
    def _prepare_request_file_vs_dir(self, request):
        '''Check if file, modify request, and return whether is a file.

        Coroutine.
        '''
        if self._url_item.url_record.link_type:
            is_file = self._url_item.url_record.link_type == LinkType.file
        elif request.url_info.path.endswith('/'):
            is_file = False
        else:
            is_file = 'unknown'

        if is_file == 'unknown':
            files = yield From(self._fetch_parent_path(request))

            if not files:
                raise Return(True)

            filename = posixpath.basename(request.file_path)

            for file_entry in files:
                if file_entry.name == filename:
                    _logger.debug('Found entry in parent. Type %s',
                                  file_entry.type)
                    is_file = file_entry.type != 'dir'
                    break
            else:
                _logger.debug('Did not find entry. Assume file.')
                raise Return(True)

            if not is_file:
                request.url = append_slash_to_path_url(request.url_info)
                _logger.debug('Request URL changed to %s. Path=%s.',
                              request.url, request.file_path)

        raise Return(is_file)

    @trollius.coroutine
    def _fetch_parent_path(self, request, use_cache=True):
        '''Fetch parent directory and return list FileEntry.

        Coroutine.
        '''
        directory_url = to_dir_path_url(request.url_info)

        if use_cache:
            if directory_url in self._processor.listing_cache:
                raise Return(self._processor.listing_cache[directory_url])

        directory_request = copy.deepcopy(request)
        directory_request.url = directory_url

        _logger.debug('Check if URL %s is file with %s.', request.url,
                      directory_url)

        with self._processor.ftp_client.session() as session:
            try:
                yield From(session.fetch_file_listing(directory_request))
            except FTPServerError:
                _logger.debug('Got an error. Assume is file.')

                if use_cache:
                    self._processor.listing_cache[directory_url] = None

                return

            temp_file = tempfile.NamedTemporaryFile(
                dir=self._processor.root_path, prefix='tmp-wpull-list'
            )

            with temp_file as file:
                directory_response = yield From(session.read_listing_content(
                    file, duration_timeout=self._fetch_rule.duration_timeout)
                )

        if use_cache:
            self._processor.listing_cache[directory_url] = \
                directory_response.files

        raise Return(directory_response.files)

    @trollius.coroutine
    def _fetch(self, request, is_file):
        '''Fetch the request

        Coroutine.
        '''
        _logger.info(_('Fetching ‘{url}’.').format(url=request.url))

        response = None

        try:
            with self._processor.ftp_client.session() as session:
                if is_file:
                    response = yield From(session.fetch(request))
                else:
                    response = yield From(session.fetch_file_listing(request))

                action = self._result_rule.handle_pre_response(
                    request, response, self._url_item
                )

                if action in (Actions.RETRY, Actions.FINISH):
                    raise HookPreResponseBreak()

                self._file_writer_session.process_response(response)

                if not response.body:
                    response.body = Body(directory=self._processor.root_path,
                                         hint='resp_cb')

                duration_timeout = self._fetch_rule.duration_timeout

                if is_file:
                    yield From(session.read_content(
                        response.body, duration_timeout=duration_timeout))
                else:
                    yield From(session.read_listing_content(
                        response.body, duration_timeout=duration_timeout))

        except HookPreResponseBreak:
            if response:
                response.body.close()

        except REMOTE_ERRORS as error:
            self._log_error(request, error)

            self._result_rule.handle_error(request, error, self._url_item)

            wait_time = self._result_rule.get_wait_time(
                request, self._url_item.url_record, error=error
            )

            if response:
                response.body.close()

            raise Return(wait_time)
        else:
            self._log_response(request, response)
            self._handle_response(request, response)

            wait_time = self._result_rule.get_wait_time(
                request, self._url_item.url_record, response=response
            )

            if is_file and \
                    self._processor.fetch_params.preserve_permissions and \
                    hasattr(response.body, 'name'):
                yield From(self._apply_unix_permissions(request, response))

            response.body.close()

            raise Return(wait_time)

    def _add_listing_links(self, response):
        '''Add links from file listing response.'''
        base_url = response.request.url_info.url
        dir_urls_to_add = set()
        file_urls_to_add = set()

        for file_entry in response.files:
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
                    linked_url_record = self._url_item.child_url_record(linked_url_info)

                    verdict = self._fetch_rule.check_ftp_request(
                        linked_url_info, linked_url_record)[0]

                    if verdict:
                        if linked_url_info.path.endswith('/'):
                            dir_urls_to_add.add(linked_url_info.url)
                        else:
                            file_urls_to_add.add(linked_url_info.url)

        self._url_item.add_child_urls(dir_urls_to_add, link_type=LinkType.directory)
        self._url_item.add_child_urls(file_urls_to_add, link_type=LinkType.file)

    def _log_response(self, request, response):
        '''Log response.'''
        _logger.info(__(
            _('Fetched ‘{url}’: {reply_code} {reply_text}. '
                'Length: {content_length}.'),
            url=request.url,
            reply_code=response.reply.code,
            reply_text=response.reply.text,
            content_length=response.body.size(),
        ))

    def _handle_response(self, request, response):
        '''Process a response.'''
        self._url_item.set_value(status_code=response.reply.code)
        is_listing = isinstance(response, ListingResponse)

        if is_listing and not self._processor.fetch_params.remove_listing or \
                not is_listing:
            filename = self._file_writer_session.save_document(response)
            action = self._result_rule.handle_document(request, response, self._url_item, filename)
        else:
            self._file_writer_session.discard_document(response)
            action = self._result_rule.handle_no_document(request, response, self._url_item)

        if isinstance(response, ListingResponse):
            self._add_listing_links(response)

        return action

    def _make_symlink(self, link_name, link_target):
        '''Make a symlink on the system.'''
        path = self._file_writer_session.extra_resource_path('dummy')

        if path:
            dir_path = os.path.dirname(path)
            symlink_path = os.path.join(dir_path, link_name)

            _logger.debug('symlink %s -> %s', symlink_path, link_target)

            os.symlink(link_target, symlink_path)

            _logger.info(__(
                _('Created symbolic link {symlink_path} to target {symlink_target}.'),
                symlink_path=symlink_path,
                symlink_target=link_target
            ))

    @trollius.coroutine
    def _apply_unix_permissions(self, request, response):
        '''Fetch and apply Unix permissions.

        Coroutine.
        '''
        files = yield From(self._fetch_parent_path(request))

        if not files:
            return

        filename = posixpath.basename(request.file_path)

        for file_entry in files:
            if file_entry.name == filename and file_entry.perm:
                _logger.debug(__(
                    'Set chmod {} o{:o}.',
                    response.body.name, file_entry.perm
                ))
                os.chmod(response.body.name, file_entry.perm)


def to_dir_path_url(url_info):
    '''Return URL string with the path replaced with directory only.'''
    dir_name = posixpath.dirname(url_info.path)

    if not dir_name.endswith('/'):
        url_template = 'ftp://{}{}/'
    else:
        url_template = 'ftp://{}{}'

    return url_template.format(url_info.hostname_with_port, dir_name)


def append_slash_to_path_url(url_info):
    '''Return URL string with the path suffixed with a slash.'''
    return 'ftp://{}{}/'.format(url_info.hostname_with_port, url_info.path)
