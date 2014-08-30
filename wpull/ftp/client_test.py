import io
import logging

from trollius import From

from wpull.ftp.client import Client
from wpull.ftp.request import Request
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
                session.fetch(Request(self.get_url('/example.txt')), file)
                )

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
                    session.fetch(Request(self.get_url('/asdf.txt')), file)
                    )
            except FTPServerError as error:
                self.assertEqual(550, error.reply_code)
            else:
                self.fail()
