'''FTP service control.'''
import logging

from trollius import From, Return
import trollius

from wpull.errors import ServerError
from wpull.ftp.request import Command
from wpull.ftp.util import ReplyCodes
import wpull.ftp.util
import wpull.string
from wpull.ftp.stream import DataStream


_logger = logging.getLogger(__name__)


class Commander(object):
    '''Helper class that performs typical FTP routines.

    Args:
        control_stream (:class:`.ftp.stream.ControlStream`): The control
            stream.
    '''
    def __init__(self, data_stream):
        self._control_stream = data_stream

    @classmethod
    def raise_if_not_match(cls, action, expected_code, reply):
        if expected_code != reply.code:
            raise ServerError(
                'Failed action {action}: {reply_code} {reply_text}'
                .format(action=action, reply_code=reply.code,
                        reply_text=wpull.string.coerce_str_to_ascii(reply.text)
                        ))

    @trollius.coroutine
    def reconnect(self):
        '''Reconnect if needed and read the welcome message.'''
        if self._control_stream.closed():
            yield From(self._control_stream.connect())
        else:
            yield From(self._control_stream.write_command(Command('REIN')))

        reply = yield From(self._control_stream.read_reply())

        self.raise_if_not_match(
            'Server ready', ReplyCodes.service_ready_for_new_user, reply)

    @trollius.coroutine
    def login(self, username='anonymous', password='-wpull-lib@'):
        '''Log in.'''
        yield From(self._control_stream.write_command(Command('USER', username)))

        reply = yield From(self._control_stream.read_reply())

        self.raise_if_not_match(
            'Login username', ReplyCodes.user_name_okay_need_password, reply)

        yield From(self._control_stream.write_command(Command('USER', password)))

        self.raise_if_not_match(
            'Login password', ReplyCodes.user_logged_in_proceed, reply)

    @trollius.coroutine
    def passive_mode(self):
        '''Enable passive mode.

        Returns:
            tuple: The address (IP address, port) of the passive port.
        '''
        yield From(self._control_stream.write_command(Command('PASV')))

        reply = yield From(self._control_stream.read_reply())

        self.raise_if_not_match(
            'Passive mode', ReplyCodes.entering_passive_mode, reply)

        return wpull.ftp.util.parse_address(reply.text)

    @trollius.coroutine
    def get_file(self, command, file, connection_factory,
                 stream_callback=None):
        '''Send a command and write stream data to file.

        This function will set up passive and binary mode and handle
        connecting to the data connection.

        Args:
            command (:class:`.ftp.request.Command`): A command that
                sends data over the data connection.
            file: A destination file object or a stream writer.
            connection_factory: A callback that returns
                :class:`.connection.Connection`.
            stream_callback: A callback that will be provided an instance of
                :class:`.ftp.stream.DataStream`.
        '''

        address = yield From(self.passive_mode())

        yield From(self._control_stream.write_command('MODE', 'I'))
        reply = yield From(self._control_stream.read_reply())

        self.raise_if_not_match('Binary mode', ReplyCodes.command_okay, reply)

        connection = connection_factory(address)
        data_stream = DataStream(connection)

        if stream_callback:
            stream_callback(data_stream)

        yield From(self.read_stream(command, file, data_stream))

    @trollius.coroutine
    def read_stream(self, command, file, data_stream):
        '''Read from the data stream.'''

        yield From(self._control_stream.write_command(command))
        reply = yield From(self._control_stream.read_reply())

        self.raise_if_not_match(
            'Begin stream',
            ReplyCodes.file_status_okay_about_to_open_data_connection,
            reply
        )

        yield From(data_stream.read_file(file=file))

        self.raise_if_not_match(
            'End stream',
            ReplyCodes.closing_data_connection,
            reply
        )

        data_stream.close()
