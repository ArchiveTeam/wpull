# encoding=utf-8
import hashlib
import zlib

from wpull.backport.testing import unittest
from wpull.decompression import DeflateDecompressor


class TestDecompression(unittest.TestCase):
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
