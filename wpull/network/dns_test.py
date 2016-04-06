# encoding=utf-8
import socket
import unittest

import wpull.testing.async
from wpull.errors import NetworkError, DNSNotFound
from wpull.network.dns import Resolver, IPFamilyPreference


DEFAULT_TIMEOUT = 30


class TestDNS(wpull.testing.async.AsyncTestCase):
    def get_resolver(self, *args, **kwargs):
        return Resolver(*args, **kwargs)

    @wpull.testing.async.async_test()
    def test_resolver(self):
        resolver = self.get_resolver()
        result = yield from resolver.resolve('google.com')

        address4 = result.first_ipv4
        address6 = result.first_ipv6

        self.assertEqual(socket.AF_INET, address4.family)
        self.assertIsInstance(address4.ip_address, str)
        self.assertIn('.', address4.ip_address)

        self.assertEqual(socket.AF_INET6, address6.family)
        self.assertIsInstance(address6.ip_address, str)
        self.assertIsInstance(address6.flow_info, int)
        self.assertIsInstance(address6.scope_id, int)
        self.assertIn(':', address6.ip_address)

    @wpull.testing.async.async_test()
    def test_resolver_localhost(self):
        resolver = self.get_resolver(family=IPFamilyPreference.ipv4_only)
        result = yield from resolver.resolve('localhost')

        address4 = result.first_ipv4
        address6 = result.first_ipv6

        self.assertEqual(socket.AF_INET, address4.family)
        self.assertIsInstance(address4.ip_address, str)
        self.assertIn('.', address4.ip_address)

        self.assertFalse(address6)

    @wpull.testing.async.async_test()
    def test_resolver_ip_address(self):
        resolver = self.get_resolver()
        result = yield from resolver.resolve('127.0.0.1')
        address4 = result.first_ipv4

        self.assertEqual(socket.AF_INET, address4.family)
        self.assertEqual('127.0.0.1', address4.ip_address)

    # TODO: figure out a good way to test other than disconnecting network
    @unittest.expectedFailure
    @wpull.testing.async.async_test()
    def test_resolver_timeout(self):
        resolver = Resolver(timeout=0.1)

        with self.assertRaises(NetworkError):
            yield from resolver.resolve('google.com')

    @wpull.testing.async.async_test()
    def test_resolver_fail(self):
        resolver = self.get_resolver()

        with self.assertRaises(DNSNotFound):
            yield from resolver.resolve('test.invalid')

    @wpull.testing.async.async_test()
    def test_resolver_fail_ipv6(self):
        resolver = self.get_resolver(family=IPFamilyPreference.ipv6_only)

        with self.assertRaises(DNSNotFound):
            yield from resolver.resolve('test.invalid')

    @wpull.testing.async.async_test()
    def test_resolver_hyphen(self):
        resolver = self.get_resolver()
        yield from resolver.resolve('-kol.deviantart.com')

    @wpull.testing.async.async_test()
    def test_resolver_rotate_cache(self):
        resolver = self.get_resolver(rotate=True, cache=Resolver.new_cache())

        for dummy in range(5):
            # FIXME: test if actual result is changed
            yield from resolver.resolve('localhost')


class TestPythonOnlyDNS(TestDNS):
    @wpull.testing.async.async_test()
    def test_dns_info_text_format(self):
        resolver = self.get_resolver()
        result = yield from resolver.resolve('google.com')

        dns_info = result.dns_infos[0]
        text = dns_info.to_text_format()
        lines = text.splitlines()

        self.assertRegex(lines[0], r'\d{14}', 'date string')
        self.assertEqual(5, len(lines[1].split()), 'resource record')


class TestNoPythonDNS(TestDNS):
    def get_resolver(self, *args, **kwargs):
        resolver = super().get_resolver(*args, **kwargs)
        resolver.dns_python_enabled = False
        return resolver

    @wpull.testing.async.async_test()
    def test_resolver_hyphen(self):
        resolver = self.get_resolver()
        with self.assertRaises(DNSNotFound):
            yield from resolver.resolve('-kol.deviantart.com')
