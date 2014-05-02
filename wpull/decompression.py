# encoding=utf-8
'''Streaming decompressors.'''
import zlib

import tornado.util


class GzipDecompressor(tornado.util.GzipDecompressor):
    '''gzip decompressor with gzip header detection.

    This class checks if the stream starts with the 2 byte gzip magic number.
    If it is not present, it returns the bytes unchanged.
    '''
    def __init__(self):
        super().__init__()
        self.checked = False
        self.is_ok = None

    def decompress(self, value):
        if self.checked:
            if self.is_ok:
                return super().decompress(value)
            else:
                return value
        else:
            # FIXME: don't assume that we receive 2 bytes or more on!
            self.checked = True
            if value[:2] == b'\x1f\x8b':
                self.is_ok = True
                return super().decompress(value)
            else:
                self.is_ok = False
                return value

    def flush(self):
        if self.is_ok:
            return super().flush()
        else:
            return b''


class DeflateDecompressor(tornado.util.GzipDecompressor):
    '''zlib decompressor with raw deflate detection.

    This class doesn't do any special. It only tries regular zlib and then
    tries raw deflate on the first decompress.
    '''
    def __init__(self):
        super().__init__()
        self.decompressobj = None

    def decompress(self, value):
        if not self.decompressobj:
            try:
                self.decompressobj = zlib.decompressobj()
                return self.decompressobj.decompress(value)
            except zlib.error:
                self.decompressobj = zlib.decompressobj(-zlib.MAX_WBITS)
                return self.decompressobj.decompress(value)

        return self.decompressobj.decompress(value)


def gzip_uncompress(data, truncated=False):
    '''Uncompress gzip data.

    Args:
        data (bytes): The gzip data.
        truncated (bool): If True, the decompressor is not flushed.

    This is a convenience function.

    Returns:
        bytes: The inflated data.

    Raises:
        zlib.error
    '''
    decompressor = tornado.util.GzipDecompressor()
    inflated_data = decompressor.decompress(data)

    if not truncated:
        inflated_data += decompressor.flush()

    return inflated_data
