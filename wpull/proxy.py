# encoding=utf-8
'''Proxy Tools'''
import gettext
import logging
import ssl
import os

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ProtocolError
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

    Attributes:
        request_callback: A callback function that accepts a Request.
        response_callback: A callback function that accepts a Request and
            Response
    '''
    def __init__(self, http_client):
        self._http_client = http_client
        self.request_callback = None
        self.response_callback = None

        self._cert_filename = wpull.util.get_package_filename('proxy.crt')
        self._key_filename = wpull.util.get_package_filename('proxy.key')

        assert os.path.isfile(self._cert_filename), self._cert_filename
        assert os.path.isfile(self._key_filename), self._key_filename

    @trollius.coroutine
    def __call__(self, reader, writer):
        '''Handle a request

        Coroutine.'''
        try:
            yield From(self._process_connection(reader, writer))
        except Exception as error:
            if not isinstance(error, StopIteration):
                if isinstance(error, (trollius.ConnectionAbortedError,
                                      trollius.ConnectionResetError)):
                    # Client using the proxy has closed the connection
                    _logger.debug('Proxy error', exc_info=True)
                else:
                    _logger.exception('Proxy error')
            else:
                raise

        writer.close()

    @trollius.coroutine
    def _process_connection(self, reader, writer):
        '''Process a connection session.'''
        _logger.debug('Begin session.')

        @trollius.coroutine
        def read_request():
            request = Request()

            for dummy in range(100):
                line = yield From(reader.readline())

                _logger.debug(__('Got line {0}', line))

                if line[-1:] != b'\n':
                    return

                if not line.strip():
                    break

                request.parse(line)
            else:
                raise ProtocolError('Request has too many headers.')

            raise Return(request)

        is_ssl_tunnel = False

        while True:
            request = yield From(read_request())

            if not request:
                return

            _logger.debug(__('Got request {0}', request))

            if request.method == 'CONNECT':
                reader, writer = yield From(self._start_tls(reader, writer))
                is_ssl_tunnel = True
                request = yield From(read_request())

                if not request:
                    return

            if is_ssl_tunnel and request.url.startswith('http://'):
                request.url = request.url.replace('http://', 'https://', 1)

            if 'Upgrade' in request.fields.get('Connection', ''):
                _logger.warning(__(
                    _('Connection Upgrade not supported for {}'),
                    request.url
                ))
                return

            if self.request_callback:
                self.request_callback(request)

            _logger.debug('Begin response.')

            with self._http_client.session() as session:
                if 'Content-Length' in request.fields:
                    request.body = reader

                response = yield From(session.fetch(request))

                if self.response_callback:
                    self.response_callback(request, response)

                writer.write(response.to_bytes())
                yield From(writer.drain())
                yield From(session.read_content(file=writer, raw=True))

            _logger.debug('Response done.')

    def _start_tls(self, reader, writer):
        '''Start SSL protocol on the socket.'''
        socket_ = writer.get_extra_info('socket')
        trollius.get_event_loop().remove_reader(socket_.fileno())

        writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
        yield From(writer.drain())

        trollius.get_event_loop().remove_writer(socket_.fileno())

        ssl_socket = ssl.wrap_socket(
            socket_, server_side=True,
            certfile=self._cert_filename,
            keyfile=self._key_filename,
            do_handshake_on_connect=False
        )

        # FIXME: this isn't how to START TLS
        for dummy in range(20):
            try:
                ssl_socket.do_handshake()
                break
            except ssl.SSLError as error:
                if error.errno in (ssl.SSL_ERROR_WANT_READ, ssl.SSL_ERROR_WANT_WRITE):
                    _logger.debug('Do handshake %s', error)
                    yield From(trollius.sleep(0.05))
                else:
                    raise
        else:
            _logger.error(_('Unable to handshake.'))
            ssl_socket.close()
            raise Return(False)

        loop = trollius.get_event_loop()
        reader = trollius.StreamReader(loop=loop)
        protocol = trollius.StreamReaderProtocol(reader, loop=loop)
        transport, dummy = yield From(loop.create_connection(
            lambda: protocol, sock=ssl_socket))
        writer = trollius.StreamWriter(transport, protocol, reader, loop)

        raise Return((reader, writer))

if __name__ == '__main__':
    from wpull.http.client import Client

    logging.basicConfig(level=logging.DEBUG)

    http_client = Client(recorder=ProgressRecorder())
    proxy = HTTPProxyServer(http_client)

    trollius.get_event_loop().run_until_complete(trollius.start_server(proxy, port=8888))
    trollius.get_event_loop().run_forever()
