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
    '''Stream class for a data connection.'''
    def __init__(self, connection):
        self._connection = connection

    def close(self):
        self._connection.close()

    @trollius.coroutine
    @close_stream_on_error
    def read_file(self, file=None):
        '''Read from connection to file.'''
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

    # TODO: def write_file()


class ControlStream(object):
    def __init__(self, connection):
        self._connection = connection
        self._data_observer = Observer()

    @property
    def data_observer(self):
        return self._data_observer

    def close(self):
        self._connection.close()

    @trollius.coroutine
    @close_stream_on_error
    def write_command(self, command):
        _logger.debug('Write command.')
        data = command.to_bytes()
        yield From(self._connection.write(data))
        self._data_observer.notify('command', data)

    @trollius.coroutine
    @close_stream_on_error
    def read_reply(self):
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
