# encoding=utf-8
import logging
import socket
import tornado.gen

from wpull.cache import Cache
from wpull.errors import NetworkError, DNSNotFound
import wpull.util
import random


_logger = logging.getLogger(__name__)


class Resolver(object):
    IPv4 = socket.AF_INET
    IPv6 = socket.AF_INET6
    global_cache = Cache(max_items=100, time_to_live=3600)

    def __init__(self, cache_enabled=True, families=(IPv4, IPv6),
    timeout=None, rotate=False):
        if cache_enabled:
            self._cache = self.global_cache
        else:
            self._cache = None

        self._families = families
        self._timeout = timeout
        self._rotate = rotate
        self._tornado_resolver = tornado.netutil.ThreadedResolver()

    @tornado.gen.coroutine
    def resolve(self, host, port):
        _logger.debug('Lookup address {0} {1}.'.format(host, port))

        addresses = []

        for family in self._families:
            results = self._get_cache(host, port, family)

            if results is not None:
                _logger.debug('DNS cache hit.')
                addresses.extend(results)
                continue

            future = self._resolve_tornado(host, port, family)
            try:
                results = yield wpull.util.wait_future(future, self._timeout)
            except wpull.util.TimedOut as error:
                raise NetworkError('DNS resolve timed out') from error

            addresses.extend(results)
            self._put_cache(host, port, family, results)

        if not addresses:
            raise DNSNotFound('DNS resolution did not return any results.')

        _logger.debug('Resolved addresses: {0}.'.format(addresses))

        if self._rotate:
            address = random.choice(addresses)
        else:
            address = addresses[0]
        _logger.debug('Selected {0} as address.'.format(address))

        raise tornado.gen.Return(address)

    @tornado.gen.coroutine
    def _resolve_tornado(self, host, port, family):
        _logger.debug('Resolving {0} {1} {2}.'.format(host, port, family))
        try:
            results = yield self._tornado_resolver.resolve(host, port, family)
            raise tornado.gen.Return(results)
        except socket.error:
            _logger.debug(
                'Failed to resolve {0} {1} {2}.'.format(host, port, family))
            raise tornado.gen.Return(())

    def _get_cache(self, host, port, family):
        if self._cache is None:
            return None

        key = (host, port, family)

        if key in self._cache:
            return self._cache[key]

    def _put_cache(self, host, port, family, results):
        key = (host, port, family)
        self._cache[key] = results
