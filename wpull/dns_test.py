# encoding=utf-8
import trollius

from wpull.dns import Resolver
from wpull.errors import NetworkError, DNSNotFound
import wpull.testing.async

from trollius import From

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
