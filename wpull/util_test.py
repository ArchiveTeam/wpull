# encoding=utf-8
import datetime
import itertools
import sys
import time
import tornado.testing
import toro
import hashlib
import zlib


from wpull.backport.testing import unittest
from wpull.util import (to_bytes, sleep, to_str, datetime_str, OrderedDefaultDict,
    wait_future, TimedOut, python_version, filter_pem, detect_encoding,
    parse_iso8601_str, printable_bytes, DeflateDecompressor, AdjustableSemaphore)


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

    def test_ordered_default_dict(self):
        mapping = OrderedDefaultDict(lambda: 2)
        mapping['a'] += 4
        mapping['b'] += 3
        mapping['c'] += 2

        self.assertEqual(
            [('a', 6), ('b', 5), ('c', 4)],
            list(mapping.items())
        )

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

    def test_deflate_decompressor(self):

        input_list = []
        hash_obj = hashlib.sha1(b'moose')

        for dummy in range(100):
            data = hash_obj.digest()
            input_list.append(data)
            hash_obj.update(data)

        input_data = b''.join(input_list)
        zlib_data = zlib.compress(input_data)
        deflate_data = zlib_data[2:-4]

        decompressor = DeflateDecompressor()
        test_data = decompressor.decompress(zlib_data[:50]) \
            + decompressor.decompress(zlib_data[50:]) \
            + decompressor.flush()

        self.assertEqual(input_data, test_data)

        decompressor = DeflateDecompressor()
        test_data = decompressor.decompress(deflate_data[:50]) \
            + decompressor.decompress(deflate_data[50:]) \
            + decompressor.flush()

        self.assertEqual(input_data, test_data)


class TestUtilAsync(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_sleep(self):
        start_time = time.time()
        yield sleep(1.0)
        end_time = time.time()

        self.assertAlmostEqual(1.0, end_time - start_time, delta=0.5)

    @tornado.testing.gen_test
    def test_wait_future(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)

        yield wait_future(test_func(), 2)

    @tornado.testing.gen_test
    def test_wait_future_none(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)

        yield wait_future(test_func(), None)

    @tornado.testing.gen_test
    def test_wait_future_timeout(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(60.0)

        try:
            yield wait_future(test_func(), 0.1)
        except TimedOut:
            pass
        else:
            self.assertTrue(False)

    @tornado.testing.gen_test
    def test_wait_future_error(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)
            raise ValueError('uh-oh')

        try:
            yield wait_future(test_func(), 2.0)
        except ValueError as error:
            self.assertEqual('uh-oh', error.args[0])
        else:
            self.assertTrue(False)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_adjustable_semaphore(self):
        semaphore = AdjustableSemaphore(value=2)

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 1
        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 2

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.set_max(3)
        self.assertEqual(3, semaphore.max)

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 3

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.set_max(1)
        self.assertEqual(1, semaphore.max)

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 2

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 1

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 0

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))

        semaphore.release()

        self.assertRaises(ValueError, semaphore.release)

        def set_neg_max():
            semaphore.set_max(-1)

        self.assertRaises(ValueError, set_neg_max)
