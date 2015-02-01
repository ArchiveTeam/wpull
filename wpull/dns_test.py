# encoding=utf-8
import socket

from trollius import From
import trollius

from wpull.dns import Resolver, PythonResolver
from wpull.errors import NetworkError, DNSNotFound
import wpull.testing.async


DEFAULT_TIMEOUT = 30


class MockFaultyResolver(Resolver):
    @trollius.coroutine
    def _resolve_from_network(self, host, port):
        yield From(trollius.sleep(2))
        yield From(Resolver._resolve_from_network(self, host, port))


class DNSMixin:
    def get_resolver_class(self):
        raise NotImplementedError()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver(self):
        resolver = self.get_resolver_class()()
        address = yield From(resolver.resolve('google.com', 80))
        self.assertTrue(address)
        self.assertEqual(2, len(address))
        self.assertIsInstance(address[0], int, 'is family')
        self.assertIsInstance(address[1][0], str, 'ip address host')
        self.assertIsInstance(address[1][1], int, 'ip address port')

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_localhost(self):
        resolver = self.get_resolver_class()(family=socket.AF_INET)
        address = yield From(resolver.resolve('localhost', 80))
        self.assertTrue(address)
        self.assertEqual(2, len(address))
        self.assertIsInstance(address[0], int, 'is family')
        self.assertIsInstance(address[1][0], str, 'ip address host')
        self.assertIsInstance(address[1][1], int, 'ip address port')

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_ip_address(self):
        resolver = self.get_resolver_class()()
        address = yield From(resolver.resolve('127.0.0.1', 80))
        self.assertEqual((socket.AF_INET, ('127.0.0.1', 80)), address)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_timeout(self):
        resolver = MockFaultyResolver(timeout=0.1)
        try:
            yield From(resolver.resolve('test.invalid', 80))
        except NetworkError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_fail(self):
        resolver = self.get_resolver_class()()
        try:
            yield From(resolver.resolve('test.invalid', 80))
        except DNSNotFound:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_ipv6(self):
        resolver = self.get_resolver_class()(family=socket.AF_INET6)

        with self.assertRaises(DNSNotFound):
            yield From(resolver.resolve('test.invalid', 80))

    def test_sort_results(self):
        Resolver_ = self.get_resolver_class()
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
            Resolver_.sort_results(results, Resolver.PREFER_IPv4)
        )

        self.assertEqual(
            [
                (socket.AF_INET6, 'ipv6-1'),
                (socket.AF_INET, 'ipv4-1'),
                (socket.AF_INET, 'ipv4-2'),
                (socket.AF_INET, 'ipv4-3'),
            ],
            Resolver_.sort_results(results, Resolver.PREFER_IPv6)
        )


class TestDNS(DNSMixin, wpull.testing.async.AsyncTestCase):
    def get_resolver_class(self):
        return Resolver

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_hyphen(self):
        resolver = self.get_resolver_class()()
        with self.assertRaises(DNSNotFound):
            yield From(resolver.resolve('-kol.deviantart.com', 80))


class TestDNSPython(DNSMixin, wpull.testing.async.AsyncTestCase):
    def get_resolver_class(self):
        return PythonResolver

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_hyphen(self):
        resolver = self.get_resolver_class()()
        yield From(resolver.resolve('-kol.deviantart.com', 80))
