import logging

from trollius import From

from wpull.ftp.client import Client
from wpull.ftp.request import Request
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase


DEFAULT_TIMEOUT = 30
_logger = logging.getLogger(__name__)


class TestClient(FTPTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_fetch_file(self):
        client = Client()

        with client.session() as session:
            response = yield From(
                session.fetch(Request(self.get_url('/example.txt')))
                )

        self.assertEqual(
            'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8'),
            response.body.content()
        )

# TODO:
#     def test_fetch_no_file(self):
