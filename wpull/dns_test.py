# encoding=utf-8
import socket

from trollius import From
import trollius

from wpull.dns import Resolver
from wpull.errors import NetworkError, DNSNotFound
import wpull.testing.async


DEFAULT_TIMEOUT = 30


class MockFaultyResolver(Resolver):
    @trollius.coroutine
    def _resolve_from_network(self, host, port):
        yield From(trollius.sleep(2))
        yield From(Resolver._resolve_from_network(self, host, port))


class TestDNS(wpull.testing.async.AsyncTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver(self):
        resolver = Resolver()
        address = yield From(resolver.resolve('google.com', 80))
        self.assertTrue(address)
        self.assertEqual(2, len(address))
        self.assertIsInstance(address[0], int, 'is family')
        self.assertIsInstance(address[1][0], str, 'ip address host')
        self.assertIsInstance(address[1][1], int, 'ip address port')

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_localhost(self):
        resolver = Resolver(family=socket.AF_INET)
        address = yield From(resolver.resolve('localhost', 80))
        self.assertTrue(address)
        self.assertEqual(2, len(address))
        self.assertIsInstance(address[0], int, 'is family')
        self.assertIsInstance(address[1][0], str, 'ip address host')
        self.assertIsInstance(address[1][1], int, 'ip address port')

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_timeout(self):
        resolver = MockFaultyResolver(timeout=0.1)
        try:
            yield From(resolver.resolve('test.invalid', 80))
        except NetworkError:
            pass
        else:
            self.fail()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_fail(self):
        resolver = Resolver()
        try:
            yield From(resolver.resolve('test.invalid', 80))
        except DNSNotFound:
            pass
        else:
            self.fail()

    def test_sort_results(self):
        results = [
            (socket.AF_INET, 'ipv4-1'),
            (socket.AF_INET, 'ipv4-2'),
            (socket.AF_INET6, 'ipv6-1'),
            (socket.AF_INET, 'ipv4-3'),
        ]

        self.assertEqual(
            [
                (socket.AF_INET, 'ipv4-1'),
                (socket.AF_INET, 'ipv4-2'),
                (socket.AF_INET, 'ipv4-3'),
                (socket.AF_INET6, 'ipv6-1'),
            ],
            Resolver.sort_results(results, Resolver.PREFER_IPv4)
        )

        self.assertEqual(
            [
                (socket.AF_INET6, 'ipv6-1'),
                (socket.AF_INET, 'ipv4-1'),
                (socket.AF_INET, 'ipv4-2'),
                (socket.AF_INET, 'ipv4-3'),
            ],
            Resolver.sort_results(results, Resolver.PREFER_IPv6)
        )
