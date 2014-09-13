import io
import logging

from trollius import From

from wpull.backport.logging import BraceMessage as __
from wpull.connection import Connection
from wpull.ftp.request import Command
from wpull.ftp.stream import ControlStream, DataStream
from wpull.ftp.util import parse_address
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase


DEFAULT_TIMEOUT = 30
_logger = logging.getLogger(__name__)


class TestStream(FTPTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_control_stream(self):
        def log_cb(data_type, data):
            _logger.debug(__('{0}={1}', data_type, data))

        connection = Connection(('127.0.0.1', self.server_port()))
        yield From(connection.connect())

        control_stream = ControlStream(connection)
        control_stream.data_observer.add(log_cb)

        reply = yield From(control_stream.read_reply())
        self.assertEqual(220, reply.code)

        yield From(control_stream.write_command(Command('USER', 'smaug')))
        reply = yield From(control_stream.read_reply())
        self.assertEqual(331, reply.code)

        yield From(control_stream.write_command(Command('PASS', 'gold1')))
        reply = yield From(control_stream.read_reply())
        self.assertEqual(230, reply.code)

        yield From(control_stream.write_command(Command('PASV')))
        reply = yield From(control_stream.read_reply())
        self.assertEqual(227, reply.code)
        address = parse_address(reply.text)

        data_connection = Connection(address)
        yield From(data_connection.connect())

        data_stream = DataStream(data_connection)

        yield From(control_stream.write_command(Command('RETR', 'example.txt')))
        reply = yield From(control_stream.read_reply())
        self.assertEqual(150, reply.code)

        my_file = io.BytesIO()

        yield From(data_stream.read_file(my_file))

        reply = yield From(control_stream.read_reply())
        self.assertEqual(226, reply.code)

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n',
            my_file.getvalue().decode('utf-8')
            )
