# encoding=utf-8
import itertools
import sys

from wpull.backport.testing import unittest
from wpull.util import (to_bytes, to_str, datetime_str,
     python_version, filter_pem, detect_encoding,
    parse_iso8601_str, printable_bytes)


DEFAULT_TIMEOUT = 30


class TestUtil(unittest.TestCase):
    def test_to_bytes(self):
        self.assertEqual(b'hi', to_bytes('hi'))
        self.assertEqual([b'hi'], to_bytes(['hi']))
        self.assertEqual({b'hi': b'hello'}, to_bytes({'hi': 'hello'}))

    def test_to_str(self):
        self.assertEqual('hi', to_str(b'hi'))
        self.assertEqual(['hi'], to_str([b'hi']))
        self.assertEqual({'hi': 'hello'}, to_str({b'hi': b'hello'}))

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

    def test_detect_encoding(self):
        mojibake = b'\x95\xb6\x8e\x9a\x89\xbb\x82\xaf'
        krakozyabry = b'\xeb\xd2\xc1\xcb\xcf\xda\xd1\xc2\xd2\xd9'

        self.assertEqual(
            'shift_jis',
            detect_encoding(mojibake, 'shift_jis')
        )
        self.assertEqual(
            'koi8-r',
            detect_encoding(krakozyabry, 'koi8-r')
        )

        self.assertEqual(
            'iso8859-1',
            detect_encoding(b'\xff\xff\xff\x81')
        )

        self.assertRaises(
            ValueError,
            detect_encoding, b'\xff\xff\xff\x81',
            'utf8', fallback=()
        )

        self.assertEqual(
            'ascii',
            detect_encoding(
                b'<html><meta charset="dog_breath"><body>',
                is_html=True
            )
        )

        self.assertEqual(
            'ascii',
            detect_encoding(
                b'<html><meta content="text/html; charset=cat-meows><body>',
                is_html=True
            )
        )

        for length in range(1, 2):
            iterable = itertools.permutations(
                [bytes(i) for i in range(256)], length
            )
            for data in iterable:
                detect_encoding(b''.join(data))

    def test_printable_bytes(self):
        self.assertEqual(
            b' 1234abc XYZ~',
            printable_bytes(b' 1234\x00abc XYZ\xff~')
        )
