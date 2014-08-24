# encoding=utf-8
'''Streaming decompressors.'''
import zlib


class SimpleGzipDecompressor(object):
    """Streaming gzip decompressor.

    The interface is like that of `zlib.decompressobj` (without some of the
    optional arguments, but it understands gzip headers and checksums.
    """
    # This class taken from tornado.util.GzipDecompressor
    # Copyright Facebook. License Apache License Version 2.0.
    def __init__(self):
        # Magic parameter makes zlib module understand gzip header
        # http://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib
        # This works on cpython and pypy, but not jython.
        self.decompressobj = zlib.decompressobj(16 + zlib.MAX_WBITS)

    def decompress(self, value):
        """Decompress a chunk, returning newly-available data.

        Some data may be buffered for later processing; `flush` must
        be called when there is no more input data to ensure that
        all data was processed.
        """
        return self.decompressobj.decompress(value)

    def flush(self):
        """Return any remaining buffered data not yet returned by decompress.

        Also checks for errors such as truncated input.
        No other methods may be called on this object after `flush`.
        """
        return self.decompressobj.flush()


class GzipDecompressor(SimpleGzipDecompressor):
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
            # XXX: gzip magic value is \x1f\x8b but data may come in as
            # a single byte. The likelyhood of plaintext starting with \x1f is
            # very low, right?
            self.checked = True
            if value[:1] == b'\x1f':
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


class DeflateDecompressor(SimpleGzipDecompressor):
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

    def flush(self):
        if self.decompressobj:
            return super().flush()
        else:
            return b''


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
    decompressor = SimpleGzipDecompressor()
    inflated_data = decompressor.decompress(data)

    if not truncated:
        inflated_data += decompressor.flush()

    return inflated_data
