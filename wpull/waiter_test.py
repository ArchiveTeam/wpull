# encoding=utf-8
import unittest

from wpull.waiter import LinearWaiter


class TestWaiter(unittest.TestCase):
    def test_linear_waiter(self):
        waiter = LinearWaiter()
        self.assertEqual(0.0, waiter.get())

        for dummy in range(5):
            waiter.increment()

        self.assertEqual(5.0, waiter.get())

        for dummy in range(50):
            waiter.increment()

        self.assertEqual(10.0, waiter.get())
