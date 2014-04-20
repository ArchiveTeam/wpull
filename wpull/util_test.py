# encoding=utf-8
import sys

from wpull.backport.testing import unittest
from wpull.util import (datetime_str, python_version, filter_pem,
    parse_iso8601_str)


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
            b'Kit\n'
        )
        clean = set([
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
        ])

        self.assertEqual(clean, filter_pem(unclean))
