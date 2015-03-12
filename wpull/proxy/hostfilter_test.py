import unittest
from wpull.proxy.hostfilter import HostFilter


class TestHostFilter(unittest.TestCase):
    def test_empty(self):
        host_filter = HostFilter()

        self.assertTrue(host_filter.test('example.com'))

    def test_domains(self):
        host_filter = HostFilter(
            accept_domains=['rayquaza.example', 'dragon.example'],
            reject_domains=['dangerous.dragon.example']
        )

        self.assertTrue(host_filter.test('rayquaza.example'))
        self.assertTrue(host_filter.test('cdn.rayquaza.example'))
        self.assertTrue(host_filter.test('dragon.example'))
        self.assertTrue(host_filter.test('.dragon.example'))
        self.assertFalse(host_filter.test('dangerous.dragon.example'))
        self.assertFalse(host_filter.test('very.dangerous.dragon.example'))
        self.assertFalse(host_filter.test('puppy.dog'))

        host_filter = HostFilter(
            reject_domains=['dangerous.dragon.example']
        )

        self.assertTrue(host_filter.test('rayquaza.example'))
        self.assertTrue(host_filter.test('cdn.rayquaza.example'))
        self.assertTrue(host_filter.test('dragon.example'))
        self.assertTrue(host_filter.test('.dragon.example'))
        self.assertFalse(host_filter.test('dangerous.dragon.example'))
        self.assertFalse(host_filter.test('very.dangerous.dragon.example'))
        self.assertTrue(host_filter.test('puppy.dog'))

    def test_hostnames(self):
        host_filter = HostFilter(
            accept_hostnames=['rayquaza.example', 'dragon.example'],
            reject_hostnames=['dangerous.dragon.example']
        )

        self.assertTrue(host_filter.test('rayquaza.example'))
        self.assertFalse(host_filter.test('cdn.rayquaza.example'))
        self.assertTrue(host_filter.test('dragon.example'))
        self.assertFalse(host_filter.test('.dragon.example'))
        self.assertFalse(host_filter.test('dangerous.dragon.example'))
        self.assertFalse(host_filter.test('very.dangerous.dragon.example'))
        self.assertFalse(host_filter.test('puppy.dog'))

        host_filter = HostFilter(
            reject_hostnames=['dangerous.dragon.example']
        )

        self.assertTrue(host_filter.test('rayquaza.example'))
        self.assertTrue(host_filter.test('cdn.rayquaza.example'))
        self.assertTrue(host_filter.test('dragon.example'))
        self.assertTrue(host_filter.test('.dragon.example'))
        self.assertFalse(host_filter.test('dangerous.dragon.example'))
        self.assertTrue(host_filter.test('very.dangerous.dragon.example'))
        self.assertTrue(host_filter.test('puppy.dog'))
