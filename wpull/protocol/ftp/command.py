'''FTP service control.'''
import logging


import asyncio
from wpull.errors import ProtocolError

from wpull.protocol.ftp.request import Command
from wpull.protocol.ftp.stream import DataStream
from wpull.protocol.ftp.util import ReplyCodes, FTPServerError
import wpull.protocol.ftp.util


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
        '''Raise FTPServerError if not expected reply code.

        Args:
            action (str): Label to use in the exception message.
            expected_code (int, list): Expected 3 digit code.
            reply (Reply): Reply from the server.
        '''
        if isinstance(expected_code, int):
            expected_codes = (expected_code,)
        else:
            expected_codes = expected_code

        if reply.code not in expected_codes:
            raise FTPServerError(
                'Failed action {action}: {reply_code} {reply_text}'
                .format(action=action, reply_code=reply.code,
                        reply_text=ascii(reply.text)
                        ),
                reply.code
                )

    @asyncio.coroutine
    def read_welcome_message(self):
        '''Read the welcome message.

        Coroutine.
        '''
        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match(
            'Server ready', ReplyCodes.service_ready_for_new_user, reply)

    @asyncio.coroutine
    def login(self, username='anonymous', password='-wpull-lib@'):
        '''Log in.

        Coroutine.
        '''
        yield from self._control_stream.write_command(Command('USER', username))

        reply = yield from self._control_stream.read_reply()

        if reply.code == ReplyCodes.user_logged_in_proceed:
            return

        self.raise_if_not_match(
            'Login username', ReplyCodes.user_name_okay_need_password, reply)

        yield from self._control_stream.write_command(Command('PASS', password))

        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match(
            'Login password', ReplyCodes.user_logged_in_proceed, reply)

    @asyncio.coroutine
    def passive_mode(self):
        '''Enable passive mode.

        Returns:
            tuple: The address (IP address, port) of the passive port.

        Coroutine.
        '''
        yield from self._control_stream.write_command(Command('PASV'))

        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match(
            'Passive mode', ReplyCodes.entering_passive_mode, reply)

        try:
            return wpull.protocol.ftp.util.parse_address(reply.text)
        except ValueError as error:
            raise ProtocolError(str(error)) from error

    @asyncio.coroutine
    def setup_data_stream(self, connection_factory,
                          data_stream_factory=DataStream):
        '''Create and setup a data stream.

        This function will set up passive and binary mode and handle
        connecting to the data connection.

        Args:
            connection_factory: A coroutine callback that returns
                :class:`.connection.Connection`.
            stream_callback: A callback that will be provided an instance of
                :class:`.ftp.stream.DataStream`.

        Coroutine.

        Returns:
            DataStream
        '''
        yield from self._control_stream.write_command(Command('TYPE', 'I'))
        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match('Binary mode', ReplyCodes.command_okay, reply)

        address = yield from self.passive_mode()

        connection = yield from connection_factory(address)

        # TODO: unit test for following line for connections that have
        # the same port over time but within pool cleaning intervals
        connection.reset()

        yield from connection.connect()

        data_stream = data_stream_factory(connection)

        return data_stream

    @asyncio.coroutine
    def begin_stream(self, command):
        '''Start sending content on the data stream.

        Args:
            command (:class:`.ftp.request.Command`): A command that
                tells the server to send data over the data connection.

        Coroutine.

        Returns:
            Reply: The begin reply.
        '''
        yield from self._control_stream.write_command(command)
        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match(
            'Begin stream',
            (
                ReplyCodes.file_status_okay_about_to_open_data_connection,
                ReplyCodes.data_connection_already_open_transfer_starting,
            ),
            reply
        )

        return reply

    @asyncio.coroutine
    def read_stream(self, file, data_stream):
        '''Read from the data stream.

        Args:
            file: A destination file object or a stream writer.
            data_stream (:class:`.ftp.stream.DataStream`): The stream of which
                to read from.

        Coroutine.

        Returns:
            Reply: The final reply.
        '''

        yield from data_stream.read_file(file=file)

        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match(
            'End stream',
            ReplyCodes.closing_data_connection,
            reply
        )

        data_stream.close()

        return reply

    @asyncio.coroutine
    def size(self, filename):
        '''Get size of file.

        Coroutine.
        '''
        yield from self._control_stream.write_command(Command('SIZE', filename))

        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match('File size', ReplyCodes.file_status, reply)

        try:
            return int(reply.text.strip())
        except ValueError:
            return

    @asyncio.coroutine
    def restart(self, offset):
        '''Send restart command.

        Coroutine.
        '''
        yield from self._control_stream.write_command(Command('REST', str(offset)))

        reply = yield from self._control_stream.read_reply()

        self.raise_if_not_match('Restart', ReplyCodes.requested_file_action_pending_further_information, reply)
