# encoding=utf-8
import time
import tornado.testing

from wpull.errors import NetworkError, DNSNotFound
from wpull.network import Resolver, BandwidthMeter
import wpull.util


DEFAULT_TIMEOUT = 30


class MockFaultyResolver(Resolver):
    @tornado.gen.coroutine
    def _resolve_tornado(self, host, port, family):
        yield wpull.util.sleep(5)
        yield Resolver._resolve_tornado(self, host, port, family)


class TestNetwork(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver(self):
        resolver = Resolver()
        address = yield resolver.resolve('google.com', 80)
        self.assertTrue(address)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_timeout(self):
        resolver = MockFaultyResolver(timeout=0.1)
        try:
            address = yield resolver.resolve('test.invalid', 80)
        except NetworkError:
            pass
        else:
            self.assertFalse(address)
            self.assertTrue(False)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_resolver_fail(self):
        resolver = Resolver()
        try:
            address = yield resolver.resolve('test.invalid', 80)
        except DNSNotFound:
            pass
        else:
            self.assertFalse(address)
            self.assertTrue(False)

    def test_bandwidth_meter(self):
        meter = BandwidthMeter()

        self.assertEqual(0, meter.speed())

        time.sleep(0.2)
        meter.feed(1000)

        self.assertTrue(meter.speed())
