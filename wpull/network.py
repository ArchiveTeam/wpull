import logging
import socket
import tornado.gen

from wpull.errors import NetworkError


_logger = logging.getLogger(__name__)


class Resolver(object):
    tornado_resolver = tornado.netutil.ThreadedResolver()

    def __init__(self, cache=True):
        # TODO: cache
        pass

    @tornado.gen.coroutine
    def resolve(self, host, port):
        _logger.debug('Lookup address {0} {1}.'.format(host, port))

        try:
            result_list = yield self.tornado_resolver.resolve(host, port)
        except socket.error as error:
            raise NetworkError(error.args[0]) from error

        if not result_list:
            raise NetworkError('No destination address.')

        # TODO: choose by IPv4/IPv6
        ip_address = result_list[0]
        _logger.debug('Selected {0} as IP address.'.format(ip_address))

        raise tornado.gen.Return(ip_address)
