from wpull.backport.testing import unittest
from wpull.factory import Factory


class TestFactory(unittest.TestCase):
    def test_factory(self):
        factory = Factory()
        factory.set('dict', dict)

        self.assertNotIn('dict', factory)

        self.assertFalse(factory.is_all_initialized())

        my_instance = factory.new('dict', [('hi', 'hello')])

        self.assertIn('dict', factory)
        self.assertEqual(my_instance, factory['dict'])
        self.assertTrue(factory.is_all_initialized())
