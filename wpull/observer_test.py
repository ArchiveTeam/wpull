import unittest

from wpull.observer import Observer


class TestObserver(unittest.TestCase):
    def test_observer(self):
        observer = Observer()

        self.assertEqual(0, observer.count())

        # Check for no crash
        observer.notify()
        observer.clear()

        self.assertRaises(KeyError, observer.remove, 'no exist')

        values = {}

        def func(value):
            values['value'] = value

        observer.add(func)

        self.assertEqual(1, observer.count())

        observer.notify('a')

        self.assertEqual('a', values['value'])

        observer.clear()
        observer.notify()

        self.assertEqual(0, observer.count())
