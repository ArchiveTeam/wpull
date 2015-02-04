# encoding=utf-8
'''DNS resolution.'''
import itertools
import logging
import random
import socket

from trollius import From, Return
import trollius
import dns.resolver

from wpull.backport.logging import BraceMessage as __
from wpull.cache import FIFOCache
from wpull.errors import DNSNotFound, NetworkError
from wpull.hook import HookableMixin, HookDisconnected
import wpull.util


_logger = logging.getLogger(__name__)


class Resolver(HookableMixin):
    '''Asynchronous resolver with cache and timeout.

    Args:
        cache_enabled (bool): If True, resolved addresses are cached.
        family: IP address family specified in :mod:`socket`. Typically
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
        assert family in (socket.AF_INET, socket.AF_INET6, self.PREFER_IPv4,
                          self.PREFER_IPv6), \
            'Unknown family {}.'.format(family)

        if cache_enabled:
            self._cache = self.global_cache
        else:
            self._cache = None

        self._family = family
        self._timeout = timeout
        self._rotate = rotate

        self.register_hook('resolve_dns')

    @trollius.coroutine
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
        _logger.debug(__('Lookup address {0} {1}.', host, port))

        host = self._lookup_hook(host, port)
        results = None

        if self._cache:
            results = self._get_cache(host, port, self._family)

        if results is None:
            results = yield From(self._resolve_from_network(host, port))

        if self._cache:
            self._put_cache(host, port, results)

        if not results:
            raise DNSNotFound(
                "DNS resolution for {0} did not return any results."
                .format(repr(host))
            )

        _logger.debug(__('Resolved addresses: {0}.', results))

        if self._rotate:
            result = random.choice(results)
        else:
            result = results[0]

        family, address = result
        _logger.debug(__('Selected {0} as address.', address))

        assert '.' in address[0] or ':' in address[0], \
            ('Resolve did not return numerical address. Got {}.'
             .format(address[0]))

        raise Return((family, address))

    def _lookup_hook(self, host, port):
        '''Return the address from callback hook'''
        try:
            new_host = self.call_hook('resolve_dns', host, port)

            if new_host:
                return new_host
            else:
                return host

        except HookDisconnected:
            pass

        return host

    @trollius.coroutine
    def _resolve_from_network(self, host, port):
        '''Resolve the address using network.

        Returns:
            list: A list of tuples.
        '''
        _logger.debug(
            'Resolving {0} {1} {2}.'.format(host, port, self._family)
        )

        try:
            future = self._getaddrinfo_implementation(host, port)
            results = yield From(trollius.wait_for(future, self._timeout))
        except trollius.TimeoutError as error:
            raise NetworkError('DNS resolve timed out.') from error
        else:
            raise Return(results)

    @trollius.coroutine
    def _getaddrinfo_implementation(self, host, port):
        '''The resolver implementation.

        Returns:
            list: A list of tuples.

            Each tuple contains:

            1. Family (``AF_INET`` or ``AF_INET6``).
            2. Address (tuple): At least two values which are
               IP address and port.

        Coroutine.
        '''
        if self._family in (self.PREFER_IPv4, self.PREFER_IPv6):
            family_flags = socket.AF_UNSPEC
        else:
            family_flags = self._family

        try:
            results = yield From(
                trollius.get_event_loop().getaddrinfo(
                    host, port, family=family_flags
                )
            )
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

        results = list([(result[0], result[4]) for result in results])

        if self._family in (self.PREFER_IPv4, self.PREFER_IPv6):
            results = self.sort_results(results, self._family)

        raise Return(results)

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
        assert preference in (cls.PREFER_IPv4, cls.PREFER_IPv6)

        ipv4_results = [
            result for result in results if result[0] == socket.AF_INET]
        ipv6_results = [
            result for result in results if result[0] == socket.AF_INET6]

        if preference == cls.PREFER_IPv6:
            return list(itertools.chain(ipv6_results, ipv4_results))
        else:
            return list(itertools.chain(ipv4_results, ipv6_results))


class PythonResolver(Resolver):
    '''Resolver using dnspython.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolver = dns.resolver.Resolver()

        if self._timeout:
            self._resolver.timeout = self._timeout

    @trollius.coroutine
    def _getaddrinfo_implementation(self, host, port):
        event_loop = trollius.get_event_loop()

        results = []

        def query_ipv4():
            answers = yield From(event_loop.run_in_executor(
                None, self._query, host, 'A'
            ))
            results.extend(
                (socket.AF_INET, (answer.address, port)) for answer in answers
            )

        def query_ipv6():
            answers = yield From(event_loop.run_in_executor(
                None, self._query, host, 'AAAA'
            ))
            results.extend(
                (socket.AF_INET6, (answer.address, port)) for answer in answers
            )

        if self._family == socket.AF_INET:
            try:
                yield From(query_ipv4())
            except DNSNotFound:
                pass
        elif self._family == socket.AF_INET6:
            try:
                yield From(query_ipv6())
            except DNSNotFound:
                pass
        else:
            try:
                yield From(query_ipv4())
            except DNSNotFound:
                pass

            try:
                yield From(query_ipv6())
            except DNSNotFound:
                pass

        if not results:
            # Maybe defined in hosts file or mDNS
            results = yield From(super()._getaddrinfo_implementation(host, port))

        raise Return(results)

    def _query(self, host, query_type):
        try:
            answer_bundle = self._resolver.query(
                host, query_type, raise_on_no_answer=False
            )
            return answer_bundle.rrset or ()
        except dns.resolver.NXDOMAIN as error:
            # dnspython doesn't raise an instance with a message, so use the
            # class name instead.
            raise DNSNotFound(
                'DNS resolution failed: {error}'
                .format(error=wpull.util.get_exception_message(error))
            ) from error
        except dns.exception.DNSException as error:
            raise NetworkError(
                'DNS resolution error: {error}'
                .format(error=wpull.util.get_exception_message(error))
            ) from error
