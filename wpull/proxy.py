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
        pre_response_callback: A callback function that accepts a Request and
            Response
        response_callback: A callback function that accepts a Request and
            Response
    '''
    def __init__(self, http_client):
        self._http_client = http_client
        self.request_callback = None
        self.pre_response_callback = None
        self.response_callback = None

    @trollius.coroutine
    def __call__(self, reader, writer):
        '''Handle a request

        Coroutine.'''
        _logger.debug('New proxy connection.')
        try:
            session = Session(
                self._http_client, reader, writer,
                self.request_callback,
                self.pre_response_callback, self.response_callback
            )
            yield From(session())
        except Exception as error:
            if not isinstance(error, StopIteration):
                if isinstance(error, (trollius.ConnectionAbortedError,
                                      trollius.ConnectionResetError)):
                    # Client using the proxy has closed the connection
                    _logger.debug('Proxy error', exc_info=True)
                else:
                    _logger.exception('Proxy error')
                writer.close()
            else:
                raise

        writer.close()
        _logger.debug('Proxy connection closed.')


class Session(object):
    '''Proxy session.'''
    def __init__(self, http_client, reader, writer, request_callback,
                 pre_response_callback, response_callback):
        self._http_client = http_client
        self._reader = self._original_reader = reader
        self._writer = self._original_writer = writer
        self._request_callback = request_callback
        self._pre_response_callback = pre_response_callback
        self._response_callback = response_callback

        self._cert_filename = wpull.util.get_package_filename('proxy.crt')
        self._key_filename = wpull.util.get_package_filename('proxy.key')

        assert os.path.isfile(self._cert_filename), self._cert_filename
        assert os.path.isfile(self._key_filename), self._key_filename

        self._is_ssl_tunnel = False

    @trollius.coroutine
    def __call__(self):
        '''Process a connection session.'''
        _logger.debug('Begin session.')

        while True:
            request = yield From(self._read_request_header())

            if not request:
                return

            _logger.debug(__('Got request {0}', request))

            if request.method == 'CONNECT':
                if self._is_ssl_tunnel:
                    self._reject_request('Cannot CONNECT within CONNECT')
                    return

                yield From(self._start_tls())
                self._is_ssl_tunnel = True
                request = yield From(self._read_request_header())

                if not request:
                    return

            if self._is_ssl_tunnel and request.url.startswith('http://'):
                request.url = request.url.replace('http://', 'https://', 1)

            if 'Upgrade' in request.fields.get('Connection', ''):
                _logger.warning(__(
                    _('Connection Upgrade not supported for {}'),
                    request.url
                ))
                self._reject_request('Upgrade not supported')
                return

            _logger.debug(__('Got request 2 {0}', request))

            if self._request_callback:
                self._request_callback(request)

            _logger.debug('Begin response.')

            with self._http_client.session() as session:
                if 'Content-Length' in request.fields:
                    request.body = self._reader

                response = yield From(session.fetch(request))

                # XXX: scripting hook tries to call to_dict() on body.
                # we set it to None so it doesn't error
                if request.body:
                    request.body = None

                if self._pre_response_callback:
                    self._pre_response_callback(request, response)

                self._writer.write(response.to_bytes())
                yield From(self._writer.drain())
                yield From(session.read_content(file=self._writer, raw=True))

                if self._response_callback:
                    self._response_callback(request, response)

            _logger.debug('Response done.')

    @trollius.coroutine
    def _read_request_header(self):
        request = Request()

        for dummy in range(100):
            line = yield From(self._reader.readline())

            _logger.debug(__('Got line {0}', line))

            if line[-1:] != b'\n':
                return

            if not line.strip():
                break

            request.parse(line)
        else:
            raise ProtocolError('Request has too many headers.')

        raise Return(request)

    def _start_tls(self):
        '''Start SSL protocol on the socket.'''
        socket_ = self._writer.get_extra_info('socket')

        try:
            trollius.get_event_loop().remove_reader(socket_.fileno())
        except ValueError as error:
            raise trollius.ConnectionAbortedError() from error

        self._writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
        yield From(self._writer.drain())

        try:
            trollius.get_event_loop().remove_writer(socket_.fileno())
        except ValueError as error:
            raise trollius.ConnectionAbortedError() from error

        ssl_socket = ssl.wrap_socket(
            socket_, server_side=True,
            certfile=self._cert_filename,
            keyfile=self._key_filename,
            do_handshake_on_connect=False
        )

        # FIXME: this isn't how to START TLS
        for dummy in range(1200):
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
            self._reject_request('Could not start TLS')
            raise trollius.ConnectionAbortedError('Could not start TLS')

        loop = trollius.get_event_loop()
        reader = trollius.StreamReader(loop=loop)
        protocol = trollius.StreamReaderProtocol(reader, loop=loop)
        transport, dummy = yield From(loop.create_connection(
            lambda: protocol, sock=ssl_socket))
        writer = trollius.StreamWriter(transport, protocol, reader, loop)

        self._reader = reader
        self._writer = writer

    def _reject_request(self, message='Request Not Allowed'):
        '''Send HTTP 501 and close the connection.'''
        self._writer.write(
            'HTTP/1.1 501 {}\r\n'.format(message).encode('ascii', 'replace')
        )
        self._writer.write(b'\r\n')
        self._writer.close()

if __name__ == '__main__':
    from wpull.http.client import Client

    logging.basicConfig(level=logging.DEBUG)

    http_client = Client(recorder=ProgressRecorder())
    proxy = HTTPProxyServer(http_client)

    trollius.get_event_loop().run_until_complete(trollius.start_server(proxy, port=8888))
    trollius.get_event_loop().run_forever()
