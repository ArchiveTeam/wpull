# encoding=utf8
'''Web processing.'''
import gettext
import io
import logging

from trollius.coroutines import Return, From
import namedlist
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.errors import NetworkError, ProtocolError, ServerError, \
    SSLVerificationError
from wpull.hook import HookableMixin, Actions
from wpull.http.web import LoopType
from wpull.namevalue import NameValueRecord
from wpull.processor.base import BaseProcessor, BaseProcessorSession, \
    REMOTE_ERRORS
from wpull.processor.rule import FetchRule, ResultRule
from wpull.stats import Statistics
from wpull.writer import NullWriter
import wpull.string
import wpull.url


_logger = logging.getLogger(__name__)
_ = gettext.gettext

WebProcessorFetchParams = namedlist.namedtuple(
    'WebProcessorFetchParamsType',
    [
        ('post_data', None),
        ('strong_redirects', True),
        ('content_on_error', False),
    ]
)
'''WebProcessorFetchParams

Args:
    post_data (str): If provided, all requests will be POSTed with the
        given `post_data`. `post_data` must be in percent-encoded
        query format ("application/x-www-form-urlencoded").
    strong_redirects (bool): If True, redirects are allowed to span hosts.
'''

WebProcessorInstances = namedlist.namedtuple(
    'WebProcessorInstancesType',
    [
        ('fetch_rule', FetchRule()),
        ('result_rule', ResultRule()),
        ('processing_rule', None),
        ('file_writer', NullWriter()),
        ('statistics', Statistics()),
        ('phantomjs_coprocessor', None),
        ('youtube_dl_coprocessor', None),
    ]
)
'''WebProcessorInstances

Args:
    fetch_rule ( :class:`.processor.rule.FetchRule`): The fetch rule.
    result_rule ( :class:`.processor.rule.ResultRule`): The result rule.
    processing_rule ( :class:`.processor.rule.ProcessingRule`): The processing rule.
    file_writer (:class`.writer.BaseWriter`): The file writer.
    phantomjs_coprocessor (:class:`.coprocessor.phantomjs.PhantomJSCoprocessor`): The PhantomJS
        corprocessor.
    youtube_dl_coprocessor (:class:`.coprocessor.youtubedl.YoutubeDlCoprocessor`): youtube-dl coprocessor.
'''


class HookPreResponseBreak(ProtocolError):
    '''Hook pre-response break.'''


class WebProcessor(BaseProcessor, HookableMixin):
    '''HTTP processor.

    Args:
        rich_client (:class:`.http.web.WebClient`): The web client.
        root_path (str): The root directory path.
        fetch_params: An instance of :class:`WebProcessorFetchParams`.
        instances: An instance of :class:`WebProcessorInstances`.

    .. seealso:: :class:`WebProcessorSession`
    '''
    DOCUMENT_STATUS_CODES = (200, 204, 206, 304,)
    '''Default status codes considered successfully fetching a document.'''

    NO_DOCUMENT_STATUS_CODES = (401, 403, 404, 405, 410,)
    '''Default status codes considered a permanent error.'''

    def __init__(self, web_client, root_path, fetch_params, instances):
        super().__init__()

        self._web_client = web_client
        self._root_path = root_path
        self._fetch_params = fetch_params
        self._instances = instances
        self._session_class = WebProcessorSession

    @property
    def web_client(self):
        '''The web client.'''
        return self._web_client

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
        '''Close the web client.'''
        self._web_client.close()


class WebProcessorSession(BaseProcessorSession):
    '''Fetches an HTTP document.

    This Processor Session will handle document redirects within the same
    Session. HTTP errors such as 404 are considered permanent errors.
    HTTP errors like 500 are considered transient errors and are handled in
    subsequence sessions by marking the item as "error".

    If a successful document has been downloaded, it will be scraped for
    URLs to be added to the URL table. This Processor Session is very simple;
    it cannot handle JavaScript or Flash plugins.
    '''
    def __init__(self, processor, url_item):
        super().__init__()
        self._processor = processor
        self._url_item = url_item
        self._file_writer_session = processor.instances.file_writer.session()
        self._web_client_session = None

        self._document_codes = WebProcessor.DOCUMENT_STATUS_CODES
        self._no_document_codes = WebProcessor.NO_DOCUMENT_STATUS_CODES

        self._request = None
        self._temp_files = set()

        self._fetch_rule = processor.instances.fetch_rule
        self._result_rule = processor.instances.result_rule
        self._processing_rule = processor.instances.processing_rule
        self._strong_redirects = self._processor.fetch_params.strong_redirects

    def _new_initial_request(self, with_body=True):
        '''Return a new Request to be passed to the Web Client.'''
        url_info = self._url_item.url_info
        url_record = self._url_item.url_record

        request = self._processor.web_client.request_factory(url_info.url)

        self._populate_common_request(request)

        if with_body:
            if url_record.post_data or self._processor.fetch_params.post_data:
                self._add_post_data(request)

            if self._file_writer_session:
                request = self._file_writer_session.process_request(request)

        return request

    def _populate_common_request(self, request):
        '''Populate the Request with common fields.'''
        url_record = self._url_item.url_record

        # Note that referrer may have already been set by the --referer option
        if url_record.referrer and not request.fields.get('Referer'):
            self._add_referrer(request, url_record, self._url_item.url_info)

        if self._fetch_rule.http_login:
            request.username, request.password = self._fetch_rule.http_login

    @classmethod
    def _add_referrer(cls, request, url_record, url_info):
        '''Add referrer URL to request.'''
        # Prohibit leak of referrer from HTTPS to HTTP
        # rfc7231 section 5.5.2.
        if url_record.referrer.startswith('https://') and \
                url_info.scheme == 'http':
            return

        request.fields['Referer'] = url_record.referrer

    @trollius.coroutine
    def process(self):
        ok = yield From(self._process_robots())

        if not ok:
            return

        self._processing_rule.add_extra_urls(self._url_item)

        self._web_client_session = self._processor.web_client.session(
            self._new_initial_request()
        )

        yield From(self._process_loop())

        if self._request and self._request.body:
            self._request.body.close()

        if not self._url_item.is_processed:
            _logger.debug('Was not processed. Skipping.')
            self._url_item.skip()

    @trollius.coroutine
    def _process_robots(self):
        '''Process robots.txt.

        Coroutine.
        '''
        try:
            request = self._new_initial_request(with_body=False)
            verdict = (yield From(self._should_fetch_reason_with_robots(
                request, self._url_item.url_record)))[0]
        except REMOTE_ERRORS as error:
            _logger.error(__(
                _('Fetching robots.txt for ‘{url}’ '
                  'encountered an error: {error}'),
                url=self._next_url_info.url, error=error
            ))
            self._result_rule.handle_error(request, error, self._url_item)

            wait_time = self._result_rule.get_wait_time()

            if wait_time:
                _logger.debug('Sleeping {0}.'.format(wait_time))
                yield From(trollius.sleep(wait_time))

            raise Return(False)
        else:
            if not verdict:
                self._url_item.skip()
                raise Return(False)

        raise Return(True)

    @trollius.coroutine
    def _process_loop(self):
        '''Fetch URL including redirects.

        Coroutine.
        '''
        while not self._web_client_session.done():
            verdict = self._should_fetch_reason(
                self._next_url_info, self._url_item.url_record)[0]

            if not verdict:
                self._url_item.skip()
                break

            self._request = self._web_client_session.next_request()

            exit_early = yield From(self._fetch_one(self._request))

            wait_time = self._result_rule.get_wait_time()

            if wait_time:
                _logger.debug('Sleeping {0}.'.format(wait_time))
                yield From(trollius.sleep(wait_time))

            if exit_early:
                break

    @trollius.coroutine
    def _fetch_one(self, request):
        '''Process one of the loop iteration.

        Coroutine.

        Returns:
            bool: If True, stop processing any future requests.
        '''
        _logger.info(_('Fetching ‘{url}’.').format(url=request.url))

        response = None

        def response_callback(dummy, callback_response):
            nonlocal response
            response = callback_response

            action = self._result_rule.handle_pre_response(
                request, response, self._url_item
            )

            if action in (Actions.RETRY, Actions.FINISH):
                raise HookPreResponseBreak()

            self._file_writer_session.process_response(response)

            if not response.body:
                response.body = Body(directory=self._processor.root_path,
                                     hint='resp_cb')

            return response.body

        try:
            response = yield From(
                self._web_client_session.fetch(callback=response_callback)
            )
        except HookPreResponseBreak:
            _logger.debug('Hook pre-response break.')
            raise Return(True)
        except REMOTE_ERRORS as error:
            self._log_error(request, error)

            action = self._result_rule.handle_error(
                request, error, self._url_item)

            if response:
                response.body.close()

            raise Return(True)
        else:
            self._log_response(request, response)
            action = self._handle_response(request, response)

            yield From(self._run_coprocessors(request, response))

            response.body.close()

            raise Return(action != Actions.NORMAL)

    def close(self):
        '''Close any temp files.'''
        for file in self._temp_files:
            file.close()

    @property
    def _next_url_info(self):
        '''Return the next URLInfo to be processed.

        This returns either the original URLInfo or the next URLinfo
        containing the redirect link.
        '''
        if not self._web_client_session:
            return self._url_item.url_info

        return self._web_client_session.next_request().url_info

    def _should_fetch_reason(self, url_info, url_record):
        '''Return info about whether the URL should be fetched.

        Returns:
            tuple: A two item tuple:

            1. bool: If True, the URL should be fetched.
            2. str: A short reason string explaining the verdict.
        '''
        is_redirect = False

        if self._strong_redirects:
            try:
                is_redirect = self._web_client_session.redirect_tracker\
                    .is_redirect()
            except AttributeError:
                pass

        return self._fetch_rule.check_subsequent_web_request(
            url_info, url_record, is_redirect=is_redirect)

    @trollius.coroutine
    def _should_fetch_reason_with_robots(self, request, url_record):
        '''Return info whether the URL should be fetched including checking
        robots.txt.

        Coroutine.
        '''
        result = yield From(
            self._fetch_rule.check_initial_web_request(request, url_record)
        )
        raise Return(result)

    def _add_post_data(self, request):
        '''Add data to the payload.'''
        if self._url_item.url_record.post_data:
            data = wpull.string.to_bytes(self._url_item.url_record.post_data)
        else:
            data = wpull.string.to_bytes(
                self._processor.fetch_params.post_data
            )

        request.method = 'POST'
        request.fields['Content-Type'] = 'application/x-www-form-urlencoded'
        request.fields['Content-Length'] = str(len(data))

        _logger.debug(__('Posting with data {0}.', data))

        if not request.body:
            request.body = Body(io.BytesIO())

        with wpull.util.reset_file_offset(request.body):
            request.body.write(data)

    def _log_response(self, request, response):
        '''Log response.'''
        _logger.info(__(
            _('Fetched ‘{url}’: {status_code} {reason}. '
                'Length: {content_length} [{content_type}].'),
            url=request.url,
            status_code=response.status_code,
            reason=wpull.string.printable_str(response.reason),
            content_length=wpull.string.printable_str(
                response.fields.get('Content-Length', _('none'))),
            content_type=wpull.string.printable_str(
                response.fields.get('Content-Type', _('none'))),
        ))

    def _handle_response(self, request, response):
        '''Process the response.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        self._url_item.set_value(status_code=response.status_code)

        if self._web_client_session.redirect_tracker.is_redirect() or \
                self._web_client_session.loop_type() == LoopType.authentication:
            self._file_writer_session.discard_document(response)

            return self._result_rule.handle_intermediate_response(
                request, response, self._url_item
            )
        elif (response.status_code in self._document_codes
              or self._processor.fetch_params.content_on_error):
            filename = self._file_writer_session.save_document(response)

            self._processing_rule.scrape_document(
                request, response, self._url_item
            )

            return self._result_rule.handle_document(
                request, response, self._url_item, filename
            )
        elif response.status_code in self._no_document_codes:
            self._file_writer_session.discard_document(response)

            return self._result_rule.handle_no_document(
                request, response, self._url_item
            )
        else:
            self._file_writer_session.discard_document(response)

            return self._result_rule.handle_document_error(
                request, response, self._url_item
            )

    def _close_instance_body(self, instance):
        '''Close any files on instance.

        This function will attempt to call ``body.close`` on
        the instance.
        '''
        if hasattr(instance, 'body'):
            instance.body.close()

    def _run_coprocessors(self, request, response):
        phantomjs_coprocessor = self._processor.instances.phantomjs_coprocessor

        if phantomjs_coprocessor:
            yield From(phantomjs_coprocessor.process(
                self._url_item, request, response, self._file_writer_session
            ))

        youtube_dl_coprocessor = self._processor.instances.youtube_dl_coprocessor

        if youtube_dl_coprocessor:
            yield From(youtube_dl_coprocessor.process(
                self._url_item, request, response, self._file_writer_session
            ))
