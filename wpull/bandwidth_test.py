# encoding=utf-8
import time

import tornado.testing

from wpull.bandwidth import BandwidthMeter


class TestNetwork(tornado.testing.AsyncTestCase):
    def test_bandwidth_meter(self):
        meter = BandwidthMeter()

        self.assertEqual(0, meter.speed())

        time.sleep(0.2)
        meter.feed(1000)

        self.assertTrue(meter.speed())
