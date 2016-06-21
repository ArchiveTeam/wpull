# encoding=utf-8
'''Proxy Tools'''
import enum
import gettext
import logging
import ssl
import os
import socket

import asyncio

import errno

from wpull.application.hook import HookableMixin, HookDisconnected
from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.errors import ProtocolError, NetworkError
from wpull.protocol.http.client import Client, Session
from wpull.protocol.http.request import Request
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class HTTPProxyServer(HookableMixin):
    '''HTTP proxy server for use with man-in-the-middle recording.

    This function is meant to be used as a callback::

        asyncio.start_server(HTTPProxyServer(HTTPClient))

    Args:
        http_client (:class:`.http.client.Client`): The HTTP client.

    Attributes:
        request_callback: A callback function that accepts a Request.
        pre_response_callback: A callback function that accepts a Request and
            Response
        response_callback: A callback function that accepts a Request and
            Response
    '''
    class Event(enum.Enum):
        begin_session = 'begin_session'
        end_session = 'end_session'

    def __init__(self, http_client: Client):
        super().__init__()
        self._http_client = http_client
        self.event_dispatcher.register(self.Event.begin_session)
        self.event_dispatcher.register(self.Event.end_session)

    @asyncio.coroutine
    def __call__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        '''Handle a request

        Coroutine.'''
        _logger.debug('New proxy connection.')
        session = self._new_session(reader, writer)
        self.event_dispatcher.notify(self.Event.begin_session, session)
        is_error = False

        try:
            yield from session()
        except Exception as error:
            if not isinstance(error, StopIteration):
                error = True
                if isinstance(error, (ConnectionAbortedError,
                                      ConnectionResetError)):
                    # Client using the proxy has closed the connection
                    _logger.debug('Proxy error', exc_info=True)
                else:
                    _logger.exception('Proxy error')
                writer.close()
            else:
                raise
        finally:
            self.event_dispatcher.notify(self.Event.end_session, session,
                                         error=is_error)

        writer.close()
        _logger.debug('Proxy connection closed.')

    def _new_session(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> 'HTTPProxySession':
        return HTTPProxySession(self._http_client, reader, writer)


class HTTPProxySession(HookableMixin):
    class Event(enum.Enum):
        client_request = 'client_request'
        server_begin_response = 'server_begin_response'
        server_end_response = 'server_end_response'
        server_response_error = 'server_response_error'

    def __init__(self, http_client: Client, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        super().__init__()
        self._http_client = http_client
        self._reader = self._original_reader = reader
        self._writer = self._original_writer = writer
        self._is_tunnel = False
        self._is_ssl_tunnel = False

        self._cert_filename = wpull.util.get_package_filename('proxy/proxy.crt')
        self._key_filename = wpull.util.get_package_filename('proxy/proxy.key')

        assert os.path.isfile(self._cert_filename), self._cert_filename
        assert os.path.isfile(self._key_filename), self._key_filename

        self.hook_dispatcher.register(self.Event.client_request)
        self.hook_dispatcher.register(self.Event.server_begin_response)
        self.event_dispatcher.register(self.Event.server_end_response)
        self.event_dispatcher.register(self.Event.server_response_error)

    @asyncio.coroutine
    def __call__(self):
        '''Process a connection session.'''
        _logger.debug('Begin session.')

        while True:
            request = yield from self._read_request_header()

            if not request:
                return

            yield from self._process_request(request)

    @asyncio.coroutine
    def _process_request(self, request: Request):
        _logger.debug(__('Got request {0}', request))

        if request.method == 'CONNECT':
            yield from self._start_connect_tunnel()
            return

        if self._is_ssl_tunnel and request.url.startswith('http://'):
            # Since we are spying under a SSL tunnel, assume processed requests
            # are SSL
            request.url = request.url.replace('http://', 'https://', 1)

        if 'Upgrade' in request.fields.get('Connection', ''):
            _logger.warning(__(
                _('Connection Upgrade not supported for {}'),
                request.url
            ))
            self._reject_request('Upgrade not supported')
            return

        _logger.debug('Begin response.')

        try:
            action = self.hook_dispatcher.call(self.Event.client_request, request)
        except HookDisconnected:
            pass
        else:
            if not action:
                _logger.debug('Proxy force reject request')
                self._reject_request()
                return

        with self._http_client.session() as session:
            if 'Content-Length' in request.fields:
                request.body = self._reader

            try:
                response = yield from session.start(request)
            except NetworkError as error:
                _logger.debug('Upstream error', exc_info=True)
                self._write_error_response()
                self.event_dispatcher.notify(self.Event.server_response_error, error)
                return

            response.body = Body()

            try:
                action = self.hook_dispatcher.call(self.Event.server_begin_response, response)
            except HookDisconnected:
                pass
            else:
                if not action:
                    _logger.debug('Proxy force reject request via response')
                    self._reject_request()
                    return

            try:
                self._writer.write(response.to_bytes())
                yield from self._writer.drain()

                session.event_dispatcher.add_listener(
                    Session.Event.response_data,
                    self._writer.write
                )

                yield from session.download(file=response.body, raw=True)

                yield from self._writer.drain()
            except NetworkError as error:
                _logger.debug('Upstream error', exc_info=True)
                self.event_dispatcher.notify(self.Event.server_response_error, error)
                raise

            self.event_dispatcher.notify(self.Event.server_end_response, response)

        _logger.debug('Response done.')

    @asyncio.coroutine
    def _start_connect_tunnel(self):
        if self._is_tunnel:
            self._reject_request('Cannot CONNECT within CONNECT')
            return

        self._is_tunnel = True

        original_socket = yield from self._detach_socket_and_start_tunnel()
        is_ssl = yield from self._is_client_request_ssl(original_socket)

        if is_ssl:
            _logger.debug('Tunneling as SSL')
            yield from self._start_ssl_tunnel()
        else:
            yield from self._rewrap_socket(original_socket)

    @classmethod
    @asyncio.coroutine
    def _is_client_request_ssl(cls, socket_: socket.socket) -> bool:
        while True:
            original_timeout = socket_.gettimeout()
            socket_.setblocking(False)

            try:
                data = socket_.recv(3, socket.MSG_PEEK)
            except OSError as error:
                if error.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    yield from asyncio.sleep(0.01)
                else:
                    raise
            else:
                break
            finally:
                socket_.settimeout(original_timeout)

        _logger.debug('peeked data %s', data)
        if all(ord('A') <= char_code <= ord('Z') for char_code in data):
            return False
        else:
            return True

    @asyncio.coroutine
    def _start_ssl_tunnel(self):
        '''Start SSL protocol on the socket.'''

        self._is_ssl_tunnel = True
        ssl_socket = yield from self._start_ssl_handshake()
        yield from self._rewrap_socket(ssl_socket)

    @asyncio.coroutine
    def _detach_socket_and_start_tunnel(self) -> socket.socket:
        socket_ = self._writer.get_extra_info('socket')

        try:
            asyncio.get_event_loop().remove_reader(socket_.fileno())
        except ValueError as error:
            raise ConnectionAbortedError() from error

        self._writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
        yield from self._writer.drain()

        try:
            asyncio.get_event_loop().remove_writer(socket_.fileno())
        except ValueError as error:
            raise ConnectionAbortedError() from error

        return socket_

    @asyncio.coroutine
    def _start_ssl_handshake(self):
        socket_ = self._writer.get_extra_info('socket')

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
                    yield from asyncio.sleep(0.05)
                else:
                    raise
        else:
            _logger.error(_('Unable to handshake.'))
            ssl_socket.close()
            self._reject_request('Could not start TLS')
            raise ConnectionAbortedError('Could not start TLS')

        return ssl_socket

    @asyncio.coroutine
    def _rewrap_socket(self, new_socket):
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader(loop=loop)
        protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
        transport, dummy = yield from loop.create_connection(
            lambda: protocol, sock=new_socket)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)

        self._reader = reader
        self._writer = writer

    @asyncio.coroutine
    def _read_request_header(self) -> Request:
        request = Request()

        for dummy in range(100):
            line = yield from self._reader.readline()

            _logger.debug(__('Got line {0}', line))

            if line[-1:] != b'\n':
                return

            if not line.strip():
                break

            request.parse(line)
        else:
            raise ProtocolError('Request has too many headers.')

        return request

    def _reject_request(self, message='Gateway Request Not Allowed'):
        '''Send HTTP 501 and close the connection.'''
        self._write_error_response(501, message)

    def _write_error_response(self, code=502, message='Bad Gateway Upstream Error'):
        self._writer.write(
            'HTTP/1.1 {} {}\r\n'.format(code, message).encode('ascii', 'replace')
        )
        self._writer.write(b'\r\n')
        self._writer.close()


def _main_test():
    from wpull.protocol.http.client import Client

    logging.basicConfig(level=logging.DEBUG)

    http_client = Client()
    proxy = HTTPProxyServer(http_client)

    asyncio.get_event_loop().run_until_complete(asyncio.start_server(proxy, port=8888))
    asyncio.get_event_loop().run_forever()


if __name__ == '__main__':
    _main_test()
