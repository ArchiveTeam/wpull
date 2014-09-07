'''Proxy support for HTTP requests.'''
from trollius import From, Return
import trollius
from wpull.errors import NetworkError
from wpull.http.request import RawRequest
from wpull.http.stream import Stream


class ProxyAdapter(object):
    '''Proxy adapter.'''
    def __init__(self, http_proxy, ssl=False, use_connect=True):
        self._http_proxy = http_proxy
        self._ssl = ssl
        self._use_connect = use_connect

    @trollius.coroutine
    def check_out(self, connection_pool):
        '''Check out a connection from the pool'''

        proxy_host, proxy_port = self._http_proxy

        connection = yield From(connection_pool.check_out(
            proxy_host, proxy_port, self._ssl))

        raise Return(connection)

    @trollius.coroutine
    def connect(self, connection_pool, connection, address, ssl=False):
        '''Connect and establish a tunnel if needed.'''
        if connection.tunneled or not ssl or not self._use_connect:
            return

        stream = Stream(connection, keep_alive=True)
        host, port = address

        request = RawRequest('CONNECT', '{0}:{1}'.format(host, port))

        yield From(stream.write_request(request))

        response = yield From(stream.read_response())

        if response.status_code == 200:
            connection.tunneled = True
            if ssl:
                raise NotImplementedError('SSL upgrading not yet supported')
            raise Return(connection)
        else:
            connection_pool.check_in(connection)
            raise NetworkError('Proxy does not support CONNECT.')
