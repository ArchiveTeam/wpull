# encoding=utf-8
'''Networking.'''
import collections
import logging
import random
import socket
import time
import tornado.gen

from wpull.cache import Cache
from wpull.errors import NetworkError, DNSNotFound
import wpull.util


_logger = logging.getLogger(__name__)


class Resolver(object):
    '''Asynchronous resolver with cache and timeout.

    Args:
        cache_enabled (bool): If True, resolved addresses are cached.
        families (iterable): A list containing the order of preferences of the
            IP address families. Only ``IPv4`` and ``IPv6`` are supported.
        timeout (int): A time in seconds used for timing-out requests. If not
            specified, this class relies on the underlying libraries.
        rotate (bool): If True and multiple addresses are resolved, randomly
            pick one.

    The cache holds 100 items and items expire after 1 hour.
    '''
    IPv4 = socket.AF_INET
    '''Constant for IPv4.'''
    IPv6 = socket.AF_INET6
    '''Constant for IPv6.'''
    global_cache = Cache(max_items=100, time_to_live=3600)
    '''The cache for resolved addresses.'''

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
        '''Resolve the given hostname and port.

        Args:
            host (str): The hostname.
            port (int): The port number.

        Returns:
            tuple: A tuple containing the address that can be passed to
            :func:`socket.connect`. Typically, the first item is the IP
            address and the second item is the port number. Note that
            IPv6 returns a tuple containing more items than 2.
        '''
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
        '''Resolve the address using Tornado.

        Returns:
            list: A list of tuples.
        '''
        _logger.debug('Resolving {0} {1} {2}.'.format(host, port, family))
        try:
            results = yield self._tornado_resolver.resolve(host, port, family)
            raise tornado.gen.Return(results)
        except socket.error:
            _logger.debug(
                'Failed to resolve {0} {1} {2}.'.format(host, port, family))
            raise tornado.gen.Return(())

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

    def _put_cache(self, host, port, family, results):
        '''Put the address in the cache.'''
        key = (host, port, family)
        self._cache[key] = results


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
