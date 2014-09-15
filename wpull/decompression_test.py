# encoding=utf-8
import gzip
import hashlib
import io
import unittest
import zlib

from wpull.decompression import DeflateDecompressor, GzipDecompressor, \
    gzip_uncompress


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

    def test_deflate_decompressor_flush(self):
        decompressor = DeflateDecompressor()
        data = decompressor.flush()
        self.assertEqual(b'', data)

    def test_gzip_decompressor(self):
        file_buffer = io.BytesIO()
        gzip_file = gzip.GzipFile(mode='wb', fileobj=file_buffer)
        gzip_file.write(b'HELLO KITTEN')
        gzip_file.close()

        decompressor = GzipDecompressor()
        data = decompressor.decompress(file_buffer.getvalue()[:5])
        data += decompressor.decompress(file_buffer.getvalue()[5:])
        data += decompressor.flush()

        self.assertEqual(b'HELLO KITTEN', data)

    def test_gzip_decompressor_flush(self):
        decompressor = GzipDecompressor()
        data = decompressor.flush()
        self.assertEqual(b'', data)

    def test_gzip_decompressor_not_gzip(self):
        decompressor = GzipDecompressor()
        data = decompressor.decompress(b'LAMMA ')
        data += decompressor.decompress(b'JUMP')
        data += decompressor.flush()

        self.assertEqual(b'LAMMA JUMP', data)

    def test_gzip_uncompress(self):
        self.assertEqual(
            b'DRAGON',
            gzip_uncompress(gzip.compress(b'DRAGON'))
            )

        # Check for no crash:
        gzip_uncompress(gzip.compress(b'DRAGON')[:1], truncated=True)
