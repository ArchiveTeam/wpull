import gettext
import logging

from wpull.backport.logging import BraceMessage as __
import wpull.string

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class ProxyCoprocessor(object):
    '''Proxy coprocessor.'''
    def __init__(self, proxy_server, cookie_jar=None):
        self._proxy_server = proxy_server
        self._cookie_jar = cookie_jar

        proxy_server.request_callback = self._request_callback
        proxy_server.pre_response_callback = self._pre_response_callback
        proxy_server.response_callback = self._response_callback

    def _request_callback(self, request):
        _logger.info(__(
            _('Fetching ‘{url}’.'),
            url=request.url_info.url
        ))

        if self._cookie_jar:
            self._cookie_jar.add_cookie_header(request)

    def _pre_response_callback(self, request, response):
        if self._cookie_jar:
            self._cookie_jar.extract_cookies(response, request)

    def _response_callback(self, request, response):
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
