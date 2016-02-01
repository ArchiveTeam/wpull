# encoding=utf8
'''Chunked transfer encoding.'''

import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ProtocolError, NetworkError


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class ChunkedTransferReader(object):
    '''Read chunked transfer encoded stream.

    Args:
        connection (:class:`.connection.Connection`): Established connection.
    '''
    def __init__(self, connection, read_size=4096):
        self._connection = connection
        self._read_size = read_size
        self._chunk_size = None
        self._bytes_left = None

    @trollius.coroutine
    def read_chunk_header(self):
        '''Read a single chunk's header.

        Returns:
            tuple: 2-item tuple with the size of the content in the chunk and
            the raw header byte string.

        Coroutine.
        '''
        # _logger.debug('Reading chunk.')

        try:
            chunk_size_hex = yield From(self._connection.readline())
        except ValueError as error:
            raise ProtocolError(
                'Invalid chunk size: {0}'.format(error)) from error

        if not chunk_size_hex.endswith(b'\n'):
            raise NetworkError('Connection closed.')

        try:
            chunk_size = int(chunk_size_hex.split(b';', 1)[0].strip(), 16)
        except ValueError as error:
            raise ProtocolError(
                'Invalid chunk size: {0}'.format(error)) from error

        if chunk_size < 0:
            raise ProtocolError('Chunk size cannot be negative.')

        self._chunk_size = self._bytes_left = chunk_size

        raise Return(chunk_size, chunk_size_hex)

    @trollius.coroutine
    def read_chunk_body(self):
        '''Read a fragment of a single chunk.

        Call :meth:`read_chunk_header` first.

        Returns:
            tuple: 2-item tuple with the content data and raw data.
            First item is empty bytes string when chunk is fully read.

        Coroutine.
        '''
        # chunk_size = self._chunk_size
        bytes_left = self._bytes_left

        # _logger.debug(__('Getting chunk size={0}, remain={1}.',
        #                 chunk_size, bytes_left))

        if bytes_left > 0:
            size = min(bytes_left, self._read_size)
            data = yield From(self._connection.read(size))

            self._bytes_left -= len(data)

            raise Return((data, data))
        elif bytes_left < 0:
            raise ProtocolError('Chunked-transfer overrun.')
        elif bytes_left:
            raise NetworkError('Connection closed.')

        newline_data = yield From(self._connection.readline())

        if len(newline_data) > 2:
            # Should be either CRLF or LF
            # This could our problem or the server's problem
            raise ProtocolError('Error reading newline after chunk.')

        self._chunk_size = self._bytes_left = None

        raise Return((b'', newline_data))

    @trollius.coroutine
    def read_trailer(self):
        '''Read the HTTP trailer fields.

        Returns:
            bytes: The trailer data.

        Coroutine.
        '''
        _logger.debug('Reading chunked trailer.')

        trailer_data_list = []

        while True:
            trailer_data = yield From(self._connection.readline())

            trailer_data_list.append(trailer_data)

            if not trailer_data.strip():
                break

        raise Return(b''.join(trailer_data_list))
