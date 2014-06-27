# encoding=utf8
'''Chunked transfer encoding.'''

import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ProtocolError, NetworkError
from wpull.observer import Observer


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class ChunkedTransferReader(object):
    '''Read chunked transfer encoded stream.

    Args:
        connection (:class:`.connection.Connection`): Established connection.

    Attributes:
        data_observer (:class:`.observer.Observer`): Called when raw data is
            read from the stream.
        content_observer (:class:`.observer.Observer`): Called when content
            data is decoded from the stream.
    '''
    def __init__(self, connection, read_size=4096):
        self._connection = connection
        self._read_size = read_size
        self.data_observer = Observer()
        self.content_observer = Observer()

    @trollius.coroutine
    def read_chunk(self):
        '''Read a single chunk of the chunked transfer encoding.

        Returns:
            int: The size of the content in the chunk.
        '''
        _logger.debug('Reading chunk.')
        chunk_size_hex = yield From(self._connection.readline())

        self.data_observer.notify(chunk_size_hex)

        if not chunk_size_hex.endswith(b'\n'):
            raise NetworkError('Connection closed.')

        try:
            chunk_size = int(chunk_size_hex.split(b';', 1)[0].strip(), 16)
        except ValueError as error:
            raise ProtocolError(error.args[0]) from error

        _logger.debug(__('Getting chunk size={0}.', chunk_size))

        if not chunk_size:
            raise Return(chunk_size)

        bytes_left = chunk_size

        while bytes_left > 0:
            data = yield From(self._connection.read(self._read_size))

            if not data:
                break

            bytes_left -= len(data)

            self.data_observer.notify(data)
            self.content_observer.notify(data)

        if bytes_left < 0:
            raise ProtocolError('Chunked-transfer overrun.')
        elif bytes_left:
            raise NetworkError('Connection closed.')

        newline_data = yield From(self._connection.readline())

        self.data_observer.notify(newline_data)

        if len(newline_data) > 2:
            # Should be either CRLF or LF
            # This could our problem or the server's problem
            raise ProtocolError('Error reading newline after chunk.')

        raise Return(chunk_size)

    @trollius.coroutine
    def read_trailer(self):
        '''Read the HTTP trailer fields.

        Returns:
            bytes: The trailer data.
        '''
        _logger.debug('Reading chunked trailer.')

        trailer_data_list = []

        while True:
            trailer_data = yield From(self._connection.readline())

            self.data_observer.notify(trailer_data)
            trailer_data_list.append(trailer_data)

            if not trailer_data.strip():
                break

        raise Return(b''.join(trailer_data_list))
