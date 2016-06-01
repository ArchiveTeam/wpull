import gettext
import logging
from http.cookiejar import CookieJar

from typing import Optional, cast

import wpull.string
from wpull.application.hook import Actions
from wpull.backport.logging import BraceMessage as __
from wpull.database.base import BaseURLTable
from wpull.pipeline.app import AppSession
from wpull.pipeline.item import URLRecord, Status
from wpull.pipeline.session import ItemSession
from wpull.processor.rule import FetchRule, ResultRule, ProcessingRule
from wpull.processor.web import WebProcessor
from wpull.protocol.http.request import Request, Response
from wpull.proxy.server import HTTPProxyServer, HTTPProxySession
from wpull.cookiewrapper import CookieJarWrapper
from wpull.writer import BaseFileWriter

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class ProxyItemSession(ItemSession):
    @property
    def is_virtual(self):
        return True

    def skip(self):
        self._processed = True
        self.set_status(Status.skipped)


class ProxyCoprocessor(object):
    '''Proxy coprocessor.'''
    def __init__(self, app_session: AppSession):
        self._app_session = app_session

        proxy_server = cast(HTTPProxyServer,
                            self._app_session.factory['HTTPProxyServer'])
        proxy_server.event_dispatcher.add_listener(
            HTTPProxyServer.Event.begin_session,
            self._proxy_server_session_callback)

    def _proxy_server_session_callback(self, session: HTTPProxySession):
        ProxyCoprocessorSession(self._app_session, session)


class ProxyCoprocessorSession(object):
    def __init__(self, app_session: AppSession,
                 http_proxy_session: HTTPProxySession):
        self._app_session = app_session
        self._http_proxy_session = http_proxy_session

        self._cookie_jar = cast(
            CookieJarWrapper, self._app_session.factory.get('CookieJarWrapper')
        )
        self._fetch_rule = cast(
            FetchRule, self._app_session.factory['FetchRule']
        )
        self._result_rule = cast(
            ResultRule, self._app_session.factory['ResultRule']
        )
        self._processing_rule = cast(
            ProcessingRule, self._app_session.factory['ProcessingRule']
        )
        file_writer = cast(
            BaseFileWriter, self._app_session.factory['FileWriter']
        )
        self._file_writer_session = file_writer.session()

        self._item_session = None

        http_proxy_session.hook_dispatcher.connect(
            HTTPProxySession.Event.client_request,
            self._client_request_callback
        )
        http_proxy_session.hook_dispatcher.connect(
            HTTPProxySession.Event.server_begin_response,
            self._server_begin_response_callback
        )
        http_proxy_session.event_dispatcher.add_listener(
            HTTPProxySession.Event.server_end_response,
            self._server_end_response_callback
        )
        http_proxy_session.event_dispatcher.add_listener(
            HTTPProxySession.Event.server_response_error,
            self._server_response_error_callback
        )

    @classmethod
    def _new_url_record(cls, request: Request) -> URLRecord:
        '''Return new empty URLRecord.'''
        url_record = URLRecord()

        url_record.url = request.url_info.url
        url_record.status = Status.in_progress
        url_record.try_count = 0
        url_record.level = 0

        return url_record

    def _new_item_session(self, request: Request) -> ProxyItemSession:
        url_table = cast(BaseURLTable, self._app_session.factory['URLTable'])
        url_table.add_one(request.url_info.url)

        return ProxyItemSession(self._app_session, self._new_url_record(request))

    def _client_request_callback(self, request: Request):
        '''Request callback handler.'''
        self._item_session = self._new_item_session(request)
        self._item_session.request = request

        if self._cookie_jar:
            self._cookie_jar.add_cookie_header(request)

        verdict, reason = self._fetch_rule.check_subsequent_web_request(self._item_session)
        self._file_writer_session.process_request(request)

        if verdict:
            _logger.info(__(
                _('Fetching ‘{url}’.'),
                url=request.url_info.url
            ))

        return verdict

    def _server_begin_response_callback(self, response: Response):
        '''Pre-response callback handler.'''
        self._item_session.response = response

        if self._cookie_jar:
            self._cookie_jar.extract_cookies(response, self._item_session.request)

        action = self._result_rule.handle_pre_response(self._item_session)
        self._file_writer_session.process_response(response)

        return action == Actions.NORMAL

    def _server_end_response_callback(self, respoonse: Response):
        '''Response callback handler.'''
        request = self._item_session.request
        response = self._item_session.response

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

        self._result_rule.handle_response(self._item_session)

        if response.status_code in WebProcessor.DOCUMENT_STATUS_CODES:
            filename = self._file_writer_session.save_document(response)
            self._processing_rule.scrape_document(self._item_session)
            self._result_rule.handle_document(self._item_session, filename)

        elif response.status_code in WebProcessor.NO_DOCUMENT_STATUS_CODES:
            self._file_writer_session.discard_document(response)
            self._result_rule.handle_no_document(self._item_session)
        else:
            self._file_writer_session.discard_document(response)
            self._result_rule.handle_document_error(self._item_session)

    def _server_response_error_callback(self, error: BaseException):
        self._result_rule.handle_error(self._item_session, error)
