import io
import logging

import asyncio
from wpull.protocol.abstract.client import DurationTimeout
from wpull.errors import ProtocolError

from wpull.protocol.ftp.client import Client
from wpull.protocol.ftp.request import Request, Command
from wpull.protocol.ftp.util import FTPServerError
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
            response = yield from \
                session.start(Request(self.get_url('/example (copy).txt')))
            yield from session.download(file)

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_duration_timeout(self):
        client = Client()
        file = io.BytesIO()

        with self.assertRaises(DurationTimeout), client.session() as session:
            yield from \
                session.start(Request(self.get_url('/hidden/sleep.txt')))
            yield from session.download(file, duration_timeout=0.1)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_no_file(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            try:
                yield from \
                    session.start(Request(self.get_url('/asdf.txt')))
                yield from session.download(file)
            except FTPServerError as error:
                self.assertEqual(550, error.reply_code)
            else:
                self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file_restart(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            request = Request(self.get_url('/example (copy).txt'))
            request.set_continue(10)
            response = yield from session.start(request)
            self.assertEqual(10, response.restart_value)
            yield from session.download(file)

        self.assertEqual(
            'reasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file_restart_not_supported(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            request = Request(self.get_url('/example (copy).txt'))
            request.set_continue(99999)  # Magic value in the test server
            response = yield from session.start(request)
            self.assertFalse(response.restart_value)
            yield from session.download(file)

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_listing(self):
        client = Client()
        file = io.BytesIO()
        with client.session() as session:
            response = yield from \
                session.start_listing(Request(self.get_url('/')))
            yield from session.download_listing(file)

        print(response.body.content())
        self.assertEqual(5, len(response.files))
        self.assertEqual('junk', response.files[0].name)
        self.assertEqual('example1', response.files[1].name)
        self.assertEqual('example2💎', response.files[2].name)
        self.assertEqual('example (copy).txt', response.files[3].name)
        self.assertEqual('readme.txt', response.files[4].name)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_bad_pasv_addr(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            original_func = session._log_in

            @asyncio.coroutine
            def override_func():
                yield from original_func()
                yield from session._control_stream.write_command(Command('EVIL_BAD_PASV_ADDR'))
                print('Evil awaits')

            # TODO: should probably have a way of sending custom commands
            session._log_in = override_func

            with self.assertRaises(ProtocolError):
                yield from \
                    session.start(Request(self.get_url('/example (copy).txt')))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_login_no_password_required(self):
        client = Client()
        file = io.BytesIO()

        with client.session() as session:
            request = Request(self.get_url('/example (copy).txt'))
            request.username = 'no_password_required'
            yield from session.start(request)
            yield from session.download(file)
