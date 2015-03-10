'''Proxy support for HTTP requests.'''
import base64

from trollius import From, Return
import trollius

from wpull.errors import NetworkError
from wpull.http.request import RawRequest
from wpull.http.stream import Stream


class ProxyAdapter(object):
    '''Proxy adapter.'''
    def __init__(self, http_proxy, ssl=False, use_connect=True,
                 authentication=None):
        self._http_proxy = http_proxy
        self._ssl = ssl
        self._use_connect = use_connect
        self._authentication = authentication
        self._auth_header_value = 'Basic {}'.format(
            base64.b64encode(
                '{}:{}'.format(authentication[0], authentication[1])
                .encode('ascii')
            ).decode('ascii')
        )

    @trollius.coroutine
    def check_out(self, connection_pool):
        '''Check out a connection from the pool.

        Coroutine.
        '''

        proxy_host, proxy_port = self._http_proxy

        connection = yield From(connection_pool.check_out(
            proxy_host, proxy_port, self._ssl))

        raise Return(connection)

    @trollius.coroutine
    def connect(self, connection_pool, connection, address, ssl=False):
        '''Connect and establish a tunnel if needed.

        Coroutine.
        '''
        if connection.tunneled or not ssl or not self._use_connect:
            return

        stream = Stream(connection, keep_alive=True)

        try:
            yield From(self._establish_tunnel(stream, address, ssl))
        except Exception as error:
            if not isinstance(error, StopIteration):
                connection_pool.check_in(connection)
            raise

    @trollius.coroutine
    def _establish_tunnel(self, stream, address, ssl=False):
        '''Establish a TCP tunnel.

        Coroutine.
        '''
        host = address[0]
        port = address[1]
        request = RawRequest('CONNECT', '{0}:{1}'.format(host, port))

        yield From(stream.write_request(request))

        response = yield From(stream.read_response())

        if response.status_code == 200:
            stream.connection.tunneled = True
            if ssl:
                raise NotImplementedError('SSL upgrading not yet supported')
            raise Return(stream.connection)
        else:
            raise NetworkError('Proxy does not support CONNECT.')

    def add_auth_header(self, request):
        '''Add the username and password to the request.'''
        if self._authentication:
            request.fields['Proxy-Authorization'] = self._auth_header_value
