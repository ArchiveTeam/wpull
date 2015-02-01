# encoding=utf-8
import time
import unittest

from wpull.bandwidth import BandwidthMeter, BandwidthLimiter


class TestNetwork(unittest.TestCase):
    def test_bandwidth_meter(self):
        meter = BandwidthMeter()

        self.assertEqual(0, meter.speed())

        meter.feed(1000, feed_time=time.time() + 0.2)

        self.assertTrue(meter.speed())

    def test_bandwidth_limit(self):
        meter = BandwidthLimiter(rate_limit=100)

        self.assertEqual(0, meter.sleep_time())

        meter.feed(1000, feed_time=time.time() + 1.0)

        self.assertAlmostEqual(9.0, meter.sleep_time(), delta=0.2)


