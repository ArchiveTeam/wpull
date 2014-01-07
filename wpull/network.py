# encoding=utf-8
import logging
import socket
import tornado.gen

from wpull.errors import NetworkError, DNSNotFound
import wpull.util


_logger = logging.getLogger(__name__)


class Resolver(object):
    IPv4 = socket.AF_INET
    IPv6 = socket.AF_INET6
    tornado_resolver = tornado.netutil.ThreadedResolver()

    def __init__(self, cache_enabled=True, families=(IPv4, IPv6),
    timeout=None):
        # TODO: cache
        self._cache_enabled = cache_enabled
        self._families = families
        self._timeout = timeout

    @tornado.gen.coroutine
    def resolve(self, host, port):
        _logger.debug('Lookup address {0} {1}.'.format(host, port))

        addresses = []

        for family in self._families:
            future = self._resolve_tornado(host, port, family)
            try:
                results = yield wpull.util.wait_future(future, self._timeout)
            except wpull.util.TimedOut as error:
                raise NetworkError('DNS resolve timed out') from error

            if results:
                addresses.extend(results)

        if not addresses:
            raise DNSNotFound('DNS resolution did not return any results.')

        _logger.debug('Resolved addresses: {0}.'.format(addresses))

        address = addresses[0]
        _logger.debug('Selected {0} as address.'.format(address))

        raise tornado.gen.Return(address)

    @tornado.gen.coroutine
    def _resolve_tornado(self, host, port, family):
        _logger.debug('Resolving {0} {1} {2}.'.format(host, port, family))
        try:
            results = yield self.tornado_resolver.resolve(host, port, family)
            raise tornado.gen.Return(results)
        except socket.error:
            _logger.debug(
                'Failed to resolve {0} {1} {2}.'.format(host, port, family))
