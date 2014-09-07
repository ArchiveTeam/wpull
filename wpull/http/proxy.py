'''Proxy support for HTTP requests.'''
from trollius import From, Return
import trollius
from wpull.errors import NetworkError
from wpull.http.request import RawRequest
from wpull.http.stream import Stream


class ProxyAdapter(object):
    '''Proxy adapter.'''
    def __init__(self, http_proxy, https_proxy):
        self._http_proxy = http_proxy
        self._https_proxy = https_proxy

    @trollius.coroutine
    def check_out(self, connection_pool, host, port, ssl):
        '''Check out a connection from the pool and establish the tunnel.'''

        if ssl:
            proxy_host, proxy_port = self._https_proxy
        else:
            proxy_host, proxy_port = self._http_proxy

        connection = yield From(connection_pool.check_out(
            proxy_host, proxy_port))

        if connection.tunneled or not ssl:
            raise Return(connection)

        stream = Stream(connection, keep_alive=True)
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
