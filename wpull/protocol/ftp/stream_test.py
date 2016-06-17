import io
import logging

import functools

import wpull.testing.async
from wpull.backport.logging import BraceMessage as __
from wpull.network.connection import Connection
from wpull.protocol.ftp.request import Command
from wpull.protocol.ftp.stream import ControlStream, DataStream
from wpull.protocol.ftp.util import parse_address
from wpull.testing.ftp import FTPTestCase

DEFAULT_TIMEOUT = 30
_logger = logging.getLogger(__name__)


class TestStream(FTPTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_control_stream(self):
        def log_cb(data_type, data):
            _logger.debug(__('{0}={1}', data_type, data))

        connection = Connection(('127.0.0.1', self.server_port()))
        yield from connection.connect()

        control_stream = ControlStream(connection)
        control_stream.data_event_dispatcher.add_read_listener(
            functools.partial(log_cb, 'read'))
        control_stream.data_event_dispatcher.add_write_listener(
            functools.partial(log_cb, 'write'))

        reply = yield from control_stream.read_reply()
        self.assertEqual(220, reply.code)

        yield from control_stream.write_command(Command('USER', 'smaug'))
        reply = yield from control_stream.read_reply()
        self.assertEqual(331, reply.code)

        yield from control_stream.write_command(Command('PASS', 'gold1'))
        reply = yield from control_stream.read_reply()
        self.assertEqual(230, reply.code)

        yield from control_stream.write_command(Command('PASV'))
        reply = yield from control_stream.read_reply()
        self.assertEqual(227, reply.code)
        address = parse_address(reply.text)

        data_connection = Connection(address)
        yield from data_connection.connect()

        data_stream = DataStream(data_connection)

        yield from control_stream.write_command(Command('RETR', 'example (copy).txt'))
        reply = yield from control_stream.read_reply()
        self.assertEqual(150, reply.code)

        my_file = io.BytesIO()

        yield from data_stream.read_file(my_file)

        reply = yield from control_stream.read_reply()
        self.assertEqual(226, reply.code)

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n',
            my_file.getvalue().decode('utf-8')
            )
