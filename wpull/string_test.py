# encoding=utf-8

import codecs
import itertools
import unittest

from wpull.string import to_bytes, to_str, detect_encoding, printable_bytes, \
    normalize_codec_name, format_size, printable_str


class TestString(unittest.TestCase):
    def test_to_bytes(self):
        self.assertEqual(b'hi', to_bytes('hi'))
        self.assertEqual([b'hi'], to_bytes(['hi']))
        self.assertEqual((b'hi', b'hello'), to_bytes(('hi', 'hello')))
        self.assertEqual({b'hi': b'hello'}, to_bytes({'hi': 'hello'}))

        object1 = object()
        self.assertEqual(object1, to_bytes(object1))

    def test_to_str(self):
        self.assertEqual('hi', to_str(b'hi'))
        self.assertEqual(['hi'], to_str([b'hi']))
        self.assertEqual(('hi', 'hello'), to_str((b'hi', b'hello')))
        self.assertEqual({'hi': 'hello'}, to_str({b'hi': b'hello'}))

        object1 = object()
        self.assertEqual(object1, to_str(object1))

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
            'shift_jis',
            detect_encoding((mojibake * 10)[:-1], 'shift_jis')
        )
        self.assertEqual(
            'koi8-r',
            detect_encoding((krakozyabry * 10)[:-1], 'koi8-r')
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
            'utf-8',
            detect_encoding(
                b'<html><meta charset="dog_breath"><body>',
                is_html=True
            )
        )

        self.assertEqual(
            'utf-8',
            detect_encoding(
                b'<html><meta content="text/html; charset=cat-meows><body>',
                is_html=True
            )
        )

        self.assertEqual(
            'utf-16-le',
            detect_encoding(
                codecs.BOM_UTF16_LE +
                'Let’s hope no one uses UTF-36'.encode('utf_16_le')[:-1]
            )
        )

        # Check for no crash
        detect_encoding(
            b'<?xml version="1.0" encoding="UTF-\xdb" ?>'
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

    def test_printable_str(self):
        self.assertEqual(
            'asdf',
            printable_str('asdf')
        )
        self.assertEqual(
            'asdf\\n',
            printable_str('asdf\n')
        )
        self.assertEqual(
            'asdf\n',
            printable_str('asdf\n', keep_newlines=True)
        )
        self.assertEqual(
            'as\\x1bdf',
            printable_str('as\x1bdf')
        )

    def test_normalize_codec_name(self):
        self.assertEqual('utf-8', normalize_codec_name('UTF-8'))
        self.assertEqual('utf-8', normalize_codec_name('uTF_8'))
        self.assertEqual('utf-8', normalize_codec_name('Utf8'))
        self.assertEqual('shift_jis', normalize_codec_name('x-sjis'))
        self.assertFalse(normalize_codec_name('\x00'))
        self.assertFalse(normalize_codec_name('wolf-howl'))
        self.assertFalse(normalize_codec_name('dragon-flatulence'))

    def test_format_size(self):
        # Check for no crash
        nums = itertools.chain(
            (-93334, -1, 0, 1, 100, 1023, 1024, 1025,),
            [10 ** expo for expo in range(1, 16)]
            )

        for num in nums:
            format_size(num)
