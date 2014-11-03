'''FTP Streams'''
import logging

from trollius import From, Return
import trollius

from wpull.abstract.stream import close_stream_on_error
from wpull.errors import NetworkError
from wpull.ftp.request import Reply
from wpull.observer import Observer


_logger = logging.getLogger(__name__)


class DataStream(object):
    '''Stream class for a data connection.

    Attributes:
        data_observer (:class:`.observer.Observer`): The data observer.
            The callback function should accept two arguments:

            1. str: The type of data. Can be ``read`` or ``write``.
            2. bytes: The raw data.

    Args:
        connection (:class:`.connection.Connection`): Connection.
    '''
    def __init__(self, connection):
        self._connection = connection
        self._data_observer = Observer()

    @property
    def data_observer(self):
        return self._data_observer

    def close(self):
        '''Close connection.'''
        self._connection.close()

    def closed(self):
        '''Return whether the connection is closed.'''
        return self._connection.closed()

    @trollius.coroutine
    @close_stream_on_error
    def read_file(self, file=None):
        '''Read from connection to file.

        Args:
            file: A file object or a writer stream.
        '''
        if file:
            file_is_async = hasattr(file, 'drain')

        while True:
            data = yield From(self._connection.read(4096))

            if not data:
                break

            if file:
                file.write(data)

                if file_is_async:
                    yield From(file.drain())

            self._data_observer.notify('read', data)

    # TODO: def write_file()


class ControlStream(object):
    '''Stream class for a control connection.

    Attributes:
        data_observer (:class:`.observer.Observer`): The data observer.
            The callback function should accept two arguments:

            1. str: The type of data. Can be ``command`` or ``reply``.
            2. bytes: The raw data.

    Args:
        connection (:class:`.connection.Connection`): Connection.
    '''
    def __init__(self, connection):
        self._connection = connection
        self._data_observer = Observer()

    @property
    def data_observer(self):
        return self._data_observer

    def close(self):
        '''Close the connection.'''
        self._connection.close()

    def closed(self):
        '''Return whether the connection is closed.'''
        return self._connection.closed()

    @trollius.coroutine
    def reconnect(self):
        '''Connected the stream if needed.

        Coroutine.
        '''
        if self._connection.closed():
            self._connection.reset()

            yield From(self._connection.connect())

    @trollius.coroutine
    @close_stream_on_error
    def write_command(self, command):
        '''Write a command to the stream.

        Args:
            command (:class:`.ftp.request.Command`): The command.

        Coroutine.
        '''
        _logger.debug('Write command.')
        data = command.to_bytes()
        yield From(self._connection.write(data))
        self._data_observer.notify('command', data)

    @trollius.coroutine
    @close_stream_on_error
    def read_reply(self):
        '''Read a reply from the stream.

        Returns:
            .ftp.request.Reply: The reply

        Coroutine.
        '''
        _logger.debug('Read reply')
        reply = Reply()

        while True:
            line = yield From(self._connection.readline())

            if line[-1:] != b'\n':
                raise NetworkError('Connection closed.')

            self._data_observer.notify('reply', line)
            reply.parse(line)

            if reply.code is not None:
                break

        raise Return(reply)
