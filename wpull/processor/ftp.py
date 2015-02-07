'''FTP'''
import gettext
import logging

from trollius.coroutines import Return, From
import namedlist
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.errors import NetworkError, ProtocolError, ServerError, \
    SSLVerificationError
from wpull.ftp.request import Request, ListingResponse, Response
from wpull.hook import Actions
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
        ('retr_symlinks', False),
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
        fetch_params: An instance of :class:`WebProcessorFetchParams`.
        instances: An instance of :class:`WebProcessorInstances`.
    '''
    def __init__(self, ftp_client, root_path, fetch_params, instances):
        super().__init__()

        self._ftp_client = ftp_client
        self._root_path = root_path
        self._fetch_params = fetch_params
        self._instances = instances
        self._session_class = FTPProcessorSession

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

        self._file_writer_session.process_request(request)

        yield From(self._fetch(request))

        wait_time = self._result_rule.get_wait_time()

        if wait_time:
            _logger.debug('Sleeping {0}.'.format(wait_time))
            yield From(trollius.sleep(wait_time))

    @trollius.coroutine
    def _fetch(self, request):
        '''Fetch the request

        Coroutine.
        '''
        _logger.info(_('Fetching ‘{url}’.').format(url=request.url))

        response = None

        is_file = not request.url_info.path.endswith('/')

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

                if is_file:
                    yield From(session.read_content(response.body))
                else:
                    yield From(session.read_listing_content(response.body))

        except HookPreResponseBreak:
            if response:
                response.body.close()

        except REMOTE_ERRORS as error:
            self._log_error(request, error)

            action = self._result_rule.handle_error(
                request, error, self._url_item)
            _logger.debug(str(self._result_rule._statistics.errors))

            if response:
                response.body.close()
        else:
            self._log_response(request, response)
            action = self._handle_response(request, response)

            response.body.close()

    def _add_listing_links(self, response):
        '''Add links from file listing response.'''
        base_url = self._url_item.url_info.url
        urls_to_add = set()

        for file_entry in response.files:
            if file_entry.type == 'dir':
                linked_url = urljoin_safe(base_url, file_entry.name + '/')
            elif file_entry.type in ('file', None):
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
                        urls_to_add.add(linked_url_info.url)

        self._url_item.add_child_urls(urls_to_add)

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
