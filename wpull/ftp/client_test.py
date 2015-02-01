import io
import logging

from trollius import From
import trollius
from wpull.errors import ProtocolError

from wpull.ftp.client import Client
from wpull.ftp.request import Request, Command
from wpull.ftp.util import FTPServerError
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase


DEFAULT_TIMEOUT = 30
_logger = logging.getLogger(__name__)


class TestClient(FTPTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            response = yield From(
                session.fetch(Request(self.get_url('/example.txt')))
                )
            yield From(session.read_content(file))

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_no_file(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            try:
                yield From(
                    session.fetch(Request(self.get_url('/asdf.txt')))
                    )
                yield From(session.read_content(file))
            except FTPServerError as error:
                self.assertEqual(550, error.reply_code)
            else:
                self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file_restart(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            request = Request(self.get_url('/example.txt'))
            request.set_continue(10)
            response = yield From(session.fetch(request))
            self.assertEqual(10, response.restart_value)
            yield From(session.read_content(file))

        self.assertEqual(
            'reasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file_restart_not_supported(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            request = Request(self.get_url('/example.txt'))
            request.set_continue(99999)  # Magic value in the test server
            response = yield From(session.fetch(request))
            self.assertFalse(response.restart_value)
            yield From(session.read_content(file))

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_listing(self):
        client = Client()
        file = io.BytesIO()
        with client.session() as session:
            response = yield From(
                session.fetch_file_listing(Request(self.get_url('/')))
            )
            yield From(session.read_listing_content(file))

        print(response.body.content())
        self.assertEqual(4, len(response.files))
        self.assertEqual('junk', response.files[0].name)
        self.assertEqual('example1', response.files[1].name)
        self.assertEqual('example2', response.files[2].name)
        self.assertEqual('example.txt', response.files[3].name)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_bad_pasv_addr(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            original_func = session._log_in

            @trollius.coroutine
            def override_func():
                yield From(original_func())
                yield From(session._control_stream.write_command(Command('EVIL_BAD_PASV_ADDR')))
                print('Evil awaits')

            session._log_in = override_func

            with self.assertRaises(ProtocolError):
                yield From(
                    session.fetch(Request(self.get_url('/example.txt')))
                )
