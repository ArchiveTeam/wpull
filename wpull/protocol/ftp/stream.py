'''FTP Streams'''
import logging


import asyncio

from typing import IO, Union

from wpull.network.connection import Connection
from wpull.protocol.abstract.stream import close_stream_on_error, \
    DataEventDispatcher
from wpull.errors import NetworkError
from wpull.protocol.ftp.request import Reply, Command


_logger = logging.getLogger(__name__)


class DataStream(object):
    '''Stream class for a data connection.

    Args:
        connection: Connection.
    '''
    def __init__(self, connection: Connection):
        self._connection = connection
        self._data_event_dispatcher = DataEventDispatcher()

    @property
    def data_event_dispatcher(self) -> DataEventDispatcher:
        return self._data_event_dispatcher

    def close(self):
        '''Close connection.'''
        self._connection.close()

    def closed(self) -> bool:
        '''Return whether the connection is closed.'''
        return self._connection.closed()

    @asyncio.coroutine
    @close_stream_on_error
    def read_file(self, file: Union[IO, asyncio.StreamWriter]=None):
        '''Read from connection to file.

        Args:
            file: A file object or a writer stream.
        '''
        if file:
            file_is_async = hasattr(file, 'drain')

        while True:
            data = yield from self._connection.read(4096)

            if not data:
                break

            if file:
                file.write(data)

                if file_is_async:
                    yield from file.drain()

            self._data_event_dispatcher.notify_read(data)

    # TODO: def write_file()


class ControlStream(object):
    '''Stream class for a control connection.

    Args:
        connection: Connection.
    '''
    def __init__(self, connection: Connection):
        self._connection = connection
        self._data_event_dispatcher = DataEventDispatcher()

    @property
    def data_event_dispatcher(self):
        return self._data_event_dispatcher

    def close(self):
        '''Close the connection.'''
        self._connection.close()

    def closed(self) -> bool:
        '''Return whether the connection is closed.'''
        return self._connection.closed()

    @asyncio.coroutine
    def reconnect(self):
        '''Connected the stream if needed.

        Coroutine.
        '''
        if self._connection.closed():
            self._connection.reset()

            yield from self._connection.connect()

    @asyncio.coroutine
    @close_stream_on_error
    def write_command(self, command: Command):
        '''Write a command to the stream.

        Args:
            command: The command.

        Coroutine.
        '''
        _logger.debug('Write command.')
        data = command.to_bytes()
        yield from self._connection.write(data)
        self._data_event_dispatcher.notify_write(data)

    @asyncio.coroutine
    @close_stream_on_error
    def read_reply(self) -> Reply:
        '''Read a reply from the stream.

        Returns:
            .ftp.request.Reply: The reply

        Coroutine.
        '''
        _logger.debug('Read reply')
        reply = Reply()

        while True:
            line = yield from self._connection.readline()

            if line[-1:] != b'\n':
                raise NetworkError('Connection closed.')

            self._data_event_dispatcher.notify_read(line)
            reply.parse(line)

            if reply.code is not None:
                break

        return reply
