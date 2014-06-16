# encoding=utf-8
'''Networking.'''
import collections
import itertools
import logging
import random
import socket
import time

import tornado.gen

import wpull.async
from wpull.cache import FIFOCache
from wpull.errors import NetworkError, DNSNotFound
from wpull.hook import HookableMixin, HookDisconnected
import wpull.string


_logger = logging.getLogger(__name__)


class Resolver(HookableMixin):
    '''Asynchronous resolver with cache and timeout.

    Args:
        cache_enabled (bool): If True, resolved addresses are cached.
        family: IP address family specified in :module:`socket`. Typically
            values are

            * :data:`socket.AF_UNSPEC`: IPv4 and/or IPv6
            * :data:`socket.AF_INET`: IPv4 only
            * :data:`socket.AF_INET6`: IPv6 only
            * :attr:`PREFER_IPv4` or :attr:`PREFER_IPv6`

        timeout (int): A time in seconds used for timing-out requests. If not
            specified, this class relies on the underlying libraries.
        rotate (bool): If True and multiple addresses are resolved, randomly
            pick one.

    The cache holds 100 items and items expire after 1 hour.
    '''
    PREFER_IPv4 = 'prefer_ipv4'
    '''Prefer IPv4 addresses.'''
    PREFER_IPv6 = 'prefer_ipv6'
    '''Prefer IPv6 addresses.'''
    global_cache = FIFOCache(max_items=100, time_to_live=3600)
    '''The cache for resolved addresses.'''

    def __init__(self, cache_enabled=True, family=PREFER_IPv4,
                 timeout=None, rotate=False):
        super().__init__()

        if cache_enabled:
            self._cache = self.global_cache
        else:
            self._cache = None

        self._family = family
        self._timeout = timeout
        self._rotate = rotate
        self._tornado_resolver = tornado.netutil.ThreadedResolver()

        self.register_hook('resolve_dns')

    @tornado.gen.coroutine
    def resolve(self, host, port):
        '''Resolve the given hostname and port.

        Args:
            host (str): The hostname.
            port (int): The port number.

        Returns:
            tuple: A tuple of length 2 where the first item is the family and
            the second item is address that can be passed
            to :func:`socket.connect`.

            Typically in an address, the first item is the IP
            family and the second item is the IP address. Note that
            IPv6 returns a tuple containing more items than 2.
        '''
        _logger.debug('Lookup address {0} {1}.'.format(host, port))

        results = self._resolve_internally(host, port)

        if results is None:
            results = yield self._resolve_from_network(host, port)

        if self._cache:
            self._put_cache(host, port, results)

        if not results:
            raise DNSNotFound(
                "DNS resolution for '{0}' did not return any results."
                .format(wpull.string.coerce_str_to_ascii(host))
            )

        _logger.debug('Resolved addresses: {0}.'.format(results))

        if self._rotate:
            result = random.choice(results)
        else:
            result = results[0]

        family, address = result
        _logger.debug('Selected {0} as address.'.format(address))

        raise tornado.gen.Return((family, address))

    def _resolve_internally(self, host, port):
        '''Resolve the address using callback hook or cache.'''
        results = None

        try:
            hook_host = self.call_hook('resolve_dns', host, port)

            if hook_host:
                family = socket.AF_INET6 if ':' in hook_host else socket.AF_INET
                results = [(family, (hook_host, port))]
        except HookDisconnected:
            pass

        if self._cache and results is None:
            results = self._get_cache(host, port, self._family)

        return results

    @tornado.gen.coroutine
    def _resolve_from_network(self, host, port):
        '''Resolve the address using Tornado.

        Returns:
            list: A list of tuples.
        '''
        _logger.debug(
            'Resolving {0} {1} {2}.'.format(host, port, self._family)
        )

        try:
            future = self._getaddrinfo_implementation(host, port)
            results = yield wpull.async.wait_future(future, self._timeout)
        except wpull.async.TimedOut as error:
            raise NetworkError('DNS resolve timed out.') from error
        except socket.error as error:
            if error.errno in (
                    socket.EAI_FAIL,
                    socket.EAI_NODATA,
                    socket.EAI_NONAME):
                raise DNSNotFound(
                    'DNS resolution failed: {error}'.format(error=error)
                ) from error
            else:
                raise NetworkError(
                    'DNS resolution error: {error}'.format(error=error)
                ) from error
        else:
            raise tornado.gen.Return(results)

    @tornado.gen.coroutine
    def _getaddrinfo_implementation(self, host, port):
        '''Call getaddrinfo.'''

        if self._family in (self.PREFER_IPv4, self.PREFER_IPv6):
            family_flags = socket.AF_UNSPEC
        else:
            family_flags = self._family

        results = yield self._tornado_resolver.resolve(
            host, port, family_flags
        )

        if self._family in (self.PREFER_IPv4, self.PREFER_IPv6):
            results = self.sort_results(results, self._family)

        raise tornado.gen.Return(results)

    def _get_cache(self, host, port, family):
        '''Return the address from cache.

        Returns:
            list, None: A list of tuples or None if the cache does not contain
            the address.
        '''
        if self._cache is None:
            return None

        key = (host, port, family)

        if key in self._cache:
            return self._cache[key]

    def _put_cache(self, host, port, results):
        '''Put the address in the cache.'''
        key = (host, port, self._family)
        self._cache[key] = results

    @classmethod
    def sort_results(cls, results, preference):
        '''Sort getaddrinfo results based on preference.'''
        ipv4_results = [
            result for result in results if result[0] == socket.AF_INET]
        ipv6_results = [
            result for result in results if result[0] == socket.AF_INET6]

        if preference == cls.PREFER_IPv6:
            return list(itertools.chain(ipv6_results, ipv4_results))
        else:
            return list(itertools.chain(ipv4_results, ipv6_results))


class BandwidthMeter(object):
    '''Calculates the speed of data transfer.

    Args:
        sample_size (int): The number of samples for measuring the speed.
        sample_min_time (float): The minimum duration between samples in
            seconds.
        stall_time (float): The time in seconds to consider no traffic
            to be connection stalled.
    '''
    def __init__(self, sample_size=20, sample_min_time=0.15, stall_time=5.0):
        self._bytes_transfered = 0
        self._samples = collections.deque(maxlen=sample_size)
        self._last_feed_time = time.time()
        self._sample_min_time = sample_min_time
        self._stall_time = stall_time
        self._stalled = False
        self._collected_bytes_transfered = 0

    @property
    def bytes_transfered(self):
        '''Return the number of bytes tranfered

        Returns:
            int
        '''
        return self._bytes_transfered

    @property
    def stalled(self):
        '''Return whether the connection is stalled.

        Returns:
            bool
        '''
        return self._stalled

    @property
    def num_samples(self):
        '''Return the number of samples collected.'''
        return len(self._samples)

    def feed(self, data_len):
        '''Update the bandwidth meter.

        Args:
            data_len (int): The number of bytes transfered since the last
                call to :func:`feed`.
        '''
        self._bytes_transfered += data_len
        self._collected_bytes_transfered += data_len

        time_now = time.time()
        time_diff = time_now - self._last_feed_time

        if time_diff < self._sample_min_time:
            return

        self._last_feed_time = time.time()

        if data_len == 0 and time_diff >= self._stall_time:
            self._stalled = True
            return

        self._samples.append((time_diff, self._collected_bytes_transfered))
        self._collected_bytes_transfered = 0

    def speed(self):
        '''Return the current transfer speed.

        Returns:
            int: The speed in bytes per second.
        '''
        if self._stalled:
            return 0

        time_sum = 0
        data_len_sum = 0

        for time_diff, data_len in self._samples:
            time_sum += time_diff
            data_len_sum += data_len

        if time_sum:
            return data_len_sum / time_sum
        else:
            return 0
