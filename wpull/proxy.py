# encoding=utf-8
'''Proxy Tools'''
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.http.request import Request
from wpull.recorder.progress import ProgressRecorder


_logger = logging.getLogger(__name__)


class HTTPProxyServer(object):
    '''HTTP proxy server for use with man-in-the-middle recording.

    This function is meant to be used as a callback::

        trollius.start_server(HTTPProxyServer(HTTPClient))

    Args:
        http_client (:class:`.http.client.Client`): The HTTP client.
        rewrite (bool): If True, strip off URLs ending with
            ``/WPULLHTTPS`` and replaces the scheme with HTTPS.
    '''
    def __init__(self, http_client, rewrite=False, cookie_jar=None):
        self._http_client = http_client
        self._rewrite = rewrite
        self._cookie_jar = cookie_jar

    @trollius.coroutine
    def __call__(self, reader, writer):
        '''Handle a request

        Coroutine.'''
        while True:
            try:
                result = yield From(self._process_request(reader, writer))
            except Exception as error:
                if not isinstance(error, StopIteration):
                    if isinstance(error, ConnectionError):
                        _logger.debug('Proxy error', exc_info=True)
                    else:
                        _logger.exception('Proxy error')

                    writer.close()
                    return

            if not result:
                writer.close()
                break

    @trollius.coroutine
    def _process_request(self, reader, writer):
        '''Process a request.'''
        _logger.debug('Begin request.')

        request = Request()

        while True:
            line = yield From(reader.readline())

            _logger.debug(__('Got line {0}', line))

            if line[-1:] != b'\n':
                return

            if not line.strip():
                break

            request.parse(line)

        _logger.debug(__('Got request {0}', request))

        if request.method == 'CONNECT':
            _logger.warning('Proxy does not support CONNECT.')
            writer.close()
            return

        if self._cookie_jar:
            self._cookie_jar.add_cookie_header(request)

        if self._rewrite and request.url.endswith('/WPULLHTTPS'):
            request.url = request.url[:-11].replace('http://', 'https://', 1)

        _logger.debug('Begin response.')

        with self._http_client.session() as session:
            if 'Content-Length' in request.fields:
                request.body = reader

            response = yield From(session.fetch(request))

            if self._cookie_jar:
                self._cookie_jar.extract_cookies(response, request)

            writer.write(response.to_bytes())
            yield From(writer.drain())
            yield From(session.read_content(file=writer, raw=True))

        _logger.debug('Response done.')

        raise Return(True)


if __name__ == '__main__':
    from wpull.http.client import Client

    logging.basicConfig(level=logging.DEBUG)

    http_client = Client(recorder=ProgressRecorder())
    proxy = HTTPProxyServer(http_client)

    trollius.get_event_loop().run_until_complete(trollius.start_server(proxy, port=8888))
    trollius.get_event_loop().run_forever()
