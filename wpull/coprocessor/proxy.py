import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.item import URLRecord, Status
import wpull.string

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class MockURLItem(object):
    '''Mock URLItem.'''
    def __init__(self, url_info, url_record):
        self.url_info = url_info
        self.url_record = url_record

    def skip(self):
        pass

    def set_status(self, dummy1, dummy2=None, dummy3=None):
        pass


class ProxyCoprocessor(object):
    '''Proxy coprocessor.'''
    def __init__(self, proxy_server, fetch_rule, result_rule, cookie_jar=None):
        self._proxy_server = proxy_server
        self._fetch_rule = fetch_rule
        self._result_rule = result_rule
        self._cookie_jar = cookie_jar

        proxy_server.request_callback = self._request_callback
        proxy_server.pre_response_callback = self._pre_response_callback
        proxy_server.response_callback = self._response_callback

    @classmethod
    def _new_url_record(cls, request):
        '''Return new empty URLRecord.'''
        return URLRecord(
            url=request.url_info.url,
            status=Status.in_progress,
            try_count=0,
            level=0,
            top_url='',
            status_code=None,
            referrer=None,
            inline=None,
            link_type=None,
            post_data=None,
            filename=None
        )

    def _request_callback(self, request):
        '''Request callback handler.'''
        if self._cookie_jar:
            self._cookie_jar.add_cookie_header(request)

        url_record = self._new_url_record(request)

        self._fetch_rule.check_subsequent_web_request(request.url_info, url_record)

        _logger.info(__(
            _('Fetching ‘{url}’.'),
            url=request.url_info.url
        ))

    def _pre_response_callback(self, request, response):
        '''Pre-response callback handler.'''
        if self._cookie_jar:
            self._cookie_jar.extract_cookies(response, request)

        url_item = MockURLItem(request.url_info, self._new_url_record(request))

        self._result_rule.handle_pre_response(request, response, url_item)

    def _response_callback(self, request, response):
        '''Response callback handler.'''
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

        url_item = MockURLItem(request.url_info, self._new_url_record(request))

        self._result_rule.handle_response(request, response, url_item)
