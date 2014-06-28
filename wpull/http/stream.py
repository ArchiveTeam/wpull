# encoding=utf8
'''HTML protocol streamers.'''
import gettext
import http.client
import itertools
import logging
import re
import zlib

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
import wpull.decompression
from wpull.errors import NetworkError, ProtocolError
from wpull.http.chunked import ChunkedTransferReader
from wpull.http.request import Response
from wpull.observer import Observer


_ = gettext.gettext
_logger = logging.getLogger(__name__)


DEFAULT_NO_CONTENT_CODES = frozenset(itertools.chain(
    range(100, 200),
    [http.client.NO_CONTENT, http.client.NOT_MODIFIED]
))
'''Status codes where a response body is prohibited.'''


class Stream(object):
    '''HTTP stream reader/writer.

    Args:
        connection (:class:`.connection.Connection`): An established
            connection.
        keep_alive (bool): If True, use HTTP keep-alive.
        ignore_length (bool): If True, Content-Length headers will be ignored.
            When using this option, `keep_alive` should be False.
    '''
    def __init__(self, connection, keep_alive=True, ignore_length=False):
        self._connection = connection
        self._keep_alive = keep_alive
        self._ignore_length = ignore_length
        self._data_observer = Observer()
        self._read_size = 4096

    @trollius.coroutine
    def write_request(self, request):
        '''Send the request's HTTP status line and header fields.'''
        _logger.debug('Sending headers.')
        data = request.to_bytes()
        self._data_observer.notify('request', data)
        yield From(self._connection.write(data))

    @trollius.coroutine
    def write_body(self, file):
        '''Send the request's content body.'''
        _logger.debug('Sending body.')

        while True:
            data = file.read(self._read_size)

            if not data:
                break

            self._data_observer.notify('request_body', data)
            yield From(self._connection.write(data))

    @trollius.coroutine
    def read_response(self, response=None):
        '''Read the response's HTTP status line and header fields.'''
        _logger.debug('Reading header.')

        if response is None:
            response = Response()

        while True:
            data = yield From(self._connection.readline())

            self._data_observer.notify('response', data)

            if not data.endswith(b'\n'):
                raise NetworkError('Connection closed.')
            elif not data:
                break

            response.parse(data)

        raise Return(response)

    @trollius.coroutine
    def read_body(self, request, response, file=None, stream=None):
        '''Read the response's content body.'''
        if is_no_body(request, response):
            return

        self._setup_decompressor(response)

        read_strategy = self.get_read_strategy(response)

        if self._ignore_length and read_strategy == 'length':
            read_strategy = 'close'

        if read_strategy == 'chunked':
            yield From(self._read_body_by_chunk(response, file, stream))
        elif read_strategy == 'length':
            yield From(self._read_body_by_length(response, file, stream))
        else:
            yield From(self._read_body_until_close(response, file, stream))

    @trollius.coroutine
    def read_body_until_close(self, response, file=None, stream=None):
        '''Read the response until the connection closes.'''
        _logger.debug('Reading body until close.')

        while True:
            data = yield From(self._connection.read(self._read_size))

            if not data:
                break

            self._data_observer.notify('response_body', data)

            content_data = self._decompress_data(data)

            if file:
                file.write(content_data)
            if stream:
                yield From(stream.write(content_data))

        content_data = self._flush_decompressor()

        if file:
            file.write(content_data)
        if stream:
            yield From(stream.write(content_data))

    @trollius.coroutine
    def _read_body_by_length(self, response, file=None, stream=None):
        '''Read the connection specified by a length.'''
        _logger.debug('Reading body by length.')

        try:
            body_size = int(response.fields['Content-Length'])

            if body_size < 0:
                raise ValueError('Content length cannot be negative.')

        except ValueError as error:
            _logger.warning(__(
                _('Invalid content length: {error}'), error=error
            ))

            yield From(self._read_body_until_close(response, file, stream))
            return

        bytes_left = body_size

        while bytes_left > 0:
            data = yield From(self._connection.read(self._read_size))

            if not data:
                break

            bytes_left -= len(data)
            self._data_observer.notify('response_body', data)

            content_data = self._decompress_data(data)

            if file:
                file.write(content_data)
            if stream:
                yield From(stream.write(content_data))

        if bytes_left < 0:
            raise ProtocolError('Content overrun.')
        elif bytes_left:
            raise NetworkError('Connection closed.')

        content_data = self._flush_decompressor()

        if file:
            file.write(content_data)
        if stream:
            yield From(stream.write(content_data))

    @trollius.coroutine
    def _read_body_by_chunk(self, response, file=None, stream=None):
        '''Read the connection using chunked transfer encoding.'''
        reader = ChunkedTransferReader(self._connection)

        while True:
            chunk_size, data = yield From(reader.read_chunk_header())

            self._data_observer.notify('response_body', data)

            if not chunk_size:
                break

            while True:
                content, data = yield From(reader.read_chunk_body())

                self._data_observer.notify('response_body', data)

                if not content:
                    break

                content = self._decompress_data(content)

                if file:
                    file.write(content)
                if stream:
                    yield From(stream.write(content))

        content = self._flush_decompressor()

        if file:
            file.write(content)
        if stream:
            yield From(stream.write(content))

        trailer_data = yield reader.read_trailer()

        self._data_observer.notify('response_body', trailer_data)

        response.fields.parse(trailer_data)

    @classmethod
    def get_read_strategy(cls, response):
        '''Return the appropriate algorithm of reading response.

        Returns:
            str: ``chunked``, ``length``, ``close``.
        '''
        chunked_match = re.match(
            r'chunked($|;)',
            response.fields.get('Transfer-Encoding', '')
        )

        if chunked_match:
            return 'chunked'
        elif 'Content-Length' in response.fields:
            return 'length'
        else:
            return 'close'

    def _setup_decompressor(self, response):
        '''Set up the content encoding decompressor.'''
        encoding = response.fields.get('Content-Encoding', '').lower()

        if encoding == 'gzip':
            self._decompressor = wpull.decompression.GzipDecompressor()
        elif encoding == 'deflate':
            self._decompressor = wpull.decompression.DeflateDecompressor()
        else:
            self._decompressor = None

    def _decompress_data(self, data):
        '''Decompress the given data and return the uncompressed data.'''
        if self._decompressor:
            try:
                return self._decompressor.decompress(data)
            except zlib.error as error:
                raise ProtocolError(
                    'zlib error: {0}.'.format(error)
                ) from error
        else:
            return data

    def _flush_decompressor(self):
        '''Return any data left in the decompressor.'''
        if self._decompressor:
            try:
                return self._decompressor.flush()
            except zlib.error as error:
                raise ProtocolError(
                    'zlib flush error: {0}.'.format(error)
                ) from error
        else:
            return b''


def is_no_body(request, response, no_content_codes=DEFAULT_NO_CONTENT_CODES):
    '''Return whether a content body is not expected.'''
    if 'Content-Length' not in response.fields \
            and 'Transfer-Encoding' not in response.fields \
            and (
                response.status_code in no_content_codes
                or request.method.upper() == 'HEAD'
            ):
        return True
    else:
        return False
