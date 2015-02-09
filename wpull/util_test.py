# encoding=utf-8
import sys
import unittest
from dns.resolver import NoNameservers

from wpull.util import (datetime_str, python_version, filter_pem,
                        parse_iso8601_str, is_ascii, close_on_error,
                        get_exception_message)


DEFAULT_TIMEOUT = 30


class TestUtil(unittest.TestCase):
    def test_datetime_str(self):
        self.assertEqual(20, len(datetime_str()))

    def test_parse_iso8601_str(self):
        self.assertEqual(10, parse_iso8601_str('1970-01-01T00:00:10Z'))

    def test_python_version(self):
        version_string = python_version()
        nums = tuple([int(n) for n in version_string.split('.')])
        self.assertEqual(3, len(nums))
        self.assertEqual(nums, sys.version_info[0:3])

    def test_filter_pem(self):
        unclean = (b'Kitten\n'
                   b'-----BEGIN CERTIFICATE-----\n'
                   b'ABCDEFG\n'
                   b'-----END CERTIFICATE-----\n'
                   b'Puppy\n'
                   b'-----BEGIN CERTIFICATE-----\n'
                   b'QWERTY\n'
                   b'-----END CERTIFICATE-----\n'
                   b'Kit\n')
        clean = {
            (
                b'-----BEGIN CERTIFICATE-----\n'
                b'ABCDEFG\n'
                b'-----END CERTIFICATE-----\n'
            ),
            (
                b'-----BEGIN CERTIFICATE-----\n'
                b'QWERTY\n'
                b'-----END CERTIFICATE-----\n'
            )
        }

        self.assertEqual(clean, filter_pem(unclean))

    def test_is_acsii(self):
        self.assertTrue(is_ascii('abc'))
        self.assertFalse(is_ascii('😤'))

    def test_close_on_error(self):
        class MyObject(object):
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def oops(self):
                with close_on_error(self.close):
                    raise ValueError()

        my_object = MyObject()
        self.assertRaises(ValueError, my_object.oops)
        self.assertTrue(my_object.closed)

    def test_get_exception_message(self):
        self.assertEqual('oops', get_exception_message(ValueError('oops')))

        try:
            raise ValueError('oops')
        except ValueError as error:
            self.assertEqual('oops', get_exception_message(error))

        self.assertEqual('ValueError', get_exception_message(ValueError()))

        try:
            raise ValueError
        except ValueError as error:
            self.assertEqual('ValueError', get_exception_message(error))

        try:
            raise ValueError()
        except ValueError as error:
            self.assertEqual('ValueError', get_exception_message(error))

        self.assertEqual(
            'NoNameservers', get_exception_message(NoNameservers())
        )

        try:
            raise NoNameservers
        except NoNameservers as error:
            self.assertEqual(
                'NoNameservers', get_exception_message(error)
            )

        try:
            raise NoNameservers()
        except NoNameservers as error:
            self.assertEqual(
                'NoNameservers', get_exception_message(error)
            )
