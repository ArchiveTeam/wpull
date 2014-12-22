# encoding=utf-8
'''Proxy Tools'''
import gettext
import logging
import ssl

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.http.request import Request
from wpull.recorder.progress import ProgressRecorder
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class HTTPProxyServer(object):
    '''HTTP proxy server for use with man-in-the-middle recording.

    This function is meant to be used as a callback::

        trollius.start_server(HTTPProxyServer(HTTPClient))

    Args:
        http_client (:class:`.http.client.Client`): The HTTP client.
    '''
    def __init__(self, http_client, cookie_jar=None):
        self._http_client = http_client
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

        is_tunnel = False
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
            socket_ = writer.get_extra_info('socket')
            trollius.get_event_loop().remove_reader(socket_.fileno())

            writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            yield From(writer.drain())

            trollius.get_event_loop().remove_writer(socket_.fileno())

            ssl_socket = ssl.wrap_socket(
                socket_, server_side=True,
                certfile=wpull.util.get_package_filename('proxy.crt'),
                keyfile=wpull.util.get_package_filename('proxy.key'),
                do_handshake_on_connect=False
            )

            # FIXME: this isn't how to START TLS
            for dummy in range(20):
                try:
                    ssl_socket.do_handshake()
                    break
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as error:
                    _logger.debug('Do handshake %s', error)
                    yield From(trollius.sleep(0.05))
            else:
                _logger.error(request.resource_path)
                _logger.error(_('Unable to handshake.'))
                ssl_socket.close()
                raise Return(False)

            loop = trollius.get_event_loop()
            reader = trollius.StreamReader(loop=loop)
            protocol = trollius.StreamReaderProtocol(reader, loop=loop)
            transport, dummy = yield from loop.create_connection(
                lambda: protocol, sock=ssl_socket)
            writer = trollius.StreamWriter(transport, protocol, reader, loop)

            is_tunnel = True

            request = Request()

            while True:
                line = yield From(reader.readline())

                _logger.debug(__('Got line {0}', line))

                if line[-1:] != b'\n':
                    return

                if not line.strip():
                    break

                request.parse(line)

            if request.url.startswith('http://'):
                request.url = request.url.replace('http://', 'https://', 1)

        if 'Upgrade' in request.fields.get('Connection', ''):
            _logger.warning(__(
                _('Connection Upgrade not supported for {}'),
                request.url
            ))
            raise Return(False)

        if self._cookie_jar:
            self._cookie_jar.add_cookie_header(request)

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

        if is_tunnel:
            # Can't reuse the connection anymore
            writer.close()
            raise Return(False)

        raise Return(True)


if __name__ == '__main__':
    from wpull.http.client import Client

    logging.basicConfig(level=logging.DEBUG)

    http_client = Client(recorder=ProgressRecorder())
    proxy = HTTPProxyServer(http_client)

    trollius.get_event_loop().run_until_complete(trollius.start_server(proxy, port=8888))
    trollius.get_event_loop().run_forever()
