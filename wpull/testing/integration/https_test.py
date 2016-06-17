import asyncio

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser
from wpull.errors import SSLVerificationError
from wpull.protocol.http.request import Request
from wpull.protocol.http.web import WebSession
from wpull.testing.integration.base import HTTPSSimpleAppTestCase
import wpull.testing.async


class TestHTTPSApp(HTTPSSimpleAppTestCase):
    @wpull.testing.async.async_test()
    def test_check_certificate(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(5, exit_code)

    @wpull.testing.async.async_test()
    def test_https_only(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/?1'),
            self.get_url('/?2').replace('https://', 'http://'),
            '--https-only',
            '--no-robots',
            '--no-check-certificate',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_ssl_bad_certificate(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-robots',
            '--no-check-certificate',
            '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)

        class MockWebSession(WebSession):
            @asyncio.coroutine
            def start(self):
                raise SSLVerificationError('A very bad certificate!')

        class MockWebClient(builder.factory.class_map['WebClient']):
            def session(self, request):
                return MockWebSession(request, self._http_client, self._redirect_tracker_factory(), Request)

        builder.factory.class_map['WebClient'] = MockWebClient

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(7, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)
