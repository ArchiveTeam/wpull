import os
import unittest

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser
from wpull.testing.integration.base import HTTPGoodAppTestCase
import wpull.testing.async
from wpull.testing.integration.http_app_test import MockDNSResolver
from wpull.testing.util import TempDirMixin
from wpull.util import IS_PYPY


class PhantomJSMixin(object):
    # FIXME: it stopped working in Travis for a while
    @unittest.skipIf(os.environ.get('TRAVIS'), 'Broken under Travis CI')
    @wpull.testing.async.async_test()
    def test_app_phantomjs(self):
        arg_parser = AppArgumentParser()
        script_filename = os.path.join(os.path.dirname(__file__),
                                       'sample_user_scripts', 'boring.plugin.py')

        # Change localhost into something else to test proxy
        args = arg_parser.parse_args([
            self.get_url('/static/simple_javascript.html').replace('localhost', 'example.invalid'),
            '--warc-file', 'test',
            '--no-warc-compression',
            '-4',
            '--no-robots',
            '--phantomjs',
            '--phantomjs-exe', 'phantomjs',
            '--phantomjs-wait', '0.1',
            '--phantomjs-scroll', '2',
            '--header', 'accept-language: dragon',
            '--plugin-script', script_filename,
            '--no-check-certificate',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        app = builder.build()
        exit_code = yield from app.run()

        self.assertTrue(os.path.exists('test.warc'))
        self.assertTrue(
            os.path.exists('simple_javascript.html.snapshot.html')
        )
        self.assertTrue(
            os.path.exists('simple_javascript.html.snapshot.pdf')
        )

        with open('simple_javascript.html.snapshot.html', 'rb') as in_file:
            data = in_file.read()
            self.assertIn(b'Hello world!', data)

        with open('test.warc', 'rb') as in_file:
            data = in_file.read()

            self.assertIn(b'urn:X-wpull:snapshot?url=', data)
            self.assertIn(b'text/html', data)
            self.assertIn(b'application/pdf', data)
            self.assertIn(b'application/json', data)
            self.assertIn(b'"set_scroll_top"', data)
            try:
                self.assertIn(b'Accept-Encoding: identity', data)
            except AssertionError:
                # webkit treats localhost differently
                self.assertNotIn(b'Accept-Encoding: gzip', data)
            self.assertIn(b'Accept-Language: dragon', data)

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @unittest.skipIf(os.environ.get('TRAVIS'), 'Broken under Travis CI')
    @wpull.testing.async.async_test(
         timeout=30 * 3 if IS_PYPY else 30
    )
    def test_app_phantomjs_scroll(self):
        arg_parser = AppArgumentParser()

        # Change localhost into something else to test proxy
        args = arg_parser.parse_args([
            self.get_url('/static/DEUUEAUGH.html').replace('localhost', 'example.invalid'),
            '-4',
            '--no-robots',
            '--phantomjs',
            '--phantomjs-wait', '0.4',
            '--phantomjs-scroll', '20',
            '--no-check-certificate',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        app = builder.build()
        exit_code = yield from app.run()

        with open('DEUUEAUGH.html.snapshot.html', 'rb') as in_file:
            data = in_file.read()
            self.assertIn(b'Count: 10', data)

        self.assertEqual(0, exit_code)


class TestPhantomJS(HTTPGoodAppTestCase, PhantomJSMixin):
    pass


class TestPhantomJSHTTPS(HTTPGoodAppTestCase, PhantomJSMixin, TempDirMixin):
    pass
