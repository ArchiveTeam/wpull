# encoding=utf-8
import contextlib
import logging
import os
import sys
import tempfile
import tornado.testing

from wpull.app import Builder
from wpull.backport.testing import unittest
from wpull.errors import ExitStatus
from wpull.options import AppArgumentParser
from wpull.testing.badapp import BadAppTestCase
from wpull.testing.goodapp import GoodAppTestCase
from http import cookiejar


try:
    from tempfile import TemporaryDirectory
except ImportError:
    from wpull.backport.tempfile import TemporaryDirectory


DEFAULT_TIMEOUT = 30


_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def cd_tempdir():
    original_dir = os.getcwd()
    with TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(original_dir)


class TestApp(GoodAppTestCase):
    def setUp(self):
        self._original_cookiejar_debug = cookiejar.debug
        cookiejar.debug = True
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    def tearDown(self):
        GoodAppTestCase.tearDown(self)
        cookiejar.debug = self._original_cookiejar_debug

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_no_args(self):
        arg_parser = AppArgumentParser(real_exit=False)
        self.assertRaises(ValueError, arg_parser.parse_args, [])

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_one_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/')])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()
            self.assertTrue(os.path.exists('index.html'))

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        cookies = list(builder.factory['CookieJar'])
        _logger.debug('{0}'.format(cookies))
        self.assertEqual(1, len(cookies))
        self.assertEqual('hi', cookies[0].name)
        self.assertEqual('hello', cookies[0].value)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_many_page_with_some_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/blog/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '-4',
        ])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()
        self.assertEqual(ExitStatus.server_error, exit_code)
        self.assertGreater(builder.factory['Statistics'].files, 1)
        self.assertGreater(builder.factory['Statistics'].duration, 3)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/').encode('utf-8'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--database', b'test.db',
            '--server-response',
            '--random-wait',
            b'--wait', b'0.1',
            '--protocol-directories',
            '--referer', 'http://test.test',
            '--accept-regex', r'.*',
            '--header', 'Hello: world!',
            '--exclude-domains', 'asdf.invalid',
            '--exclude-hostnames', 'qwerty.invalid,uiop.invalid',
            '--no-clobber',
            '--rotate-dns',
            '-4',
            '--concurrent', '2',
            '--no-check-certificate',
            '--ascii-print',
            '--progress', 'dot',
            '--secure-protocol', 'TLSv1',
            '--convert-links', '--backup-converted',
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()

            print(list(os.walk('.')))
            self.assertTrue(os.path.exists('http/localhost/index.html'))
            self.assertTrue(os.path.exists('http/localhost/index.html.orig'))

        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_input_file_arg(self):
        arg_parser = AppArgumentParser(real_exit=False)
        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(self.get_url('/').encode('utf-8'))
            in_file.write(b'\n')
            in_file.write(self.get_url('/blog/').encode('utf-8'))
            in_file.flush()

            args = arg_parser.parse_args([
                '--input-file', in_file.name
            ])
            with cd_tempdir():
                engine = Builder(args).build()
                exit_code = yield engine()
        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--warc-file', 'test',
            '-4',
            '--no-robots',
            '--no-warc-digests',
        ])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()

            self.assertTrue(os.path.exists('test.warc.gz'))

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc_with_cdx(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--warc-file', 'test',
            '-4',
            '--no-robots',
            '--warc-cdx',
        ])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_post_data(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/post/'),
            '--post-data', 'text=hi',
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_sanity(self):
        arg_items = [
            ('--verbose', '--quiet'),
            ('--timestamp', '--no-clobber'),
            ('--inet4-only', '--inet6-only'),
            ('--warc-file=test', '--no-clobber'),
            ('--warc-file=test', '--timestamping'),
            ('--warc-file=test', '--continue'),
            ('--lua-script=blah.lua', '--python-script=blah.py'),
        ]

        for arg_item in arg_items:
            def print_(message=None):
                print(message)

            def test_exit(status=0, message=None):
                raise ValueError(status, message)

            arg_parser = AppArgumentParser()
            arg_parser.exit = test_exit
            arg_parser.print_help = print_
            arg_parser.print_usage = print_

            try:
                print(arg_item)
                arg_parser.parse_args([self.get_url('/')] + list(arg_item))
            except ValueError as error:
                self.assertEqual(2, error.args[0])
            else:
                self.assertTrue(False)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_python_script(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
            'testing', 'py_hook_script.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--python-script', filename,
            '--page-requisites',
            '--reject-regex', '/post/',
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(42, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_python_script_stop(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
            'testing', 'py_hook_script_stop.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--python-script', filename,
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(1, exit_code)

    @unittest.skipIf(sys.version_info[0:2] == (3, 2),
        'lua module not working in this python version')
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_lua_script(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
            'testing', 'lua_hook_script.lua')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--lua-script', filename,
            '--page-requisites',
            '--reject-regex', '/post/',
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(42, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_iri_handling(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/mojibake.html')])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_cookie(self):
        arg_parser = AppArgumentParser()

        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(b'# Netscape HTTP Cookie File\n')
            in_file.write(b'localhost.local')
            in_file.write(b'\tFALSE\t/\tFALSE\t\ttest\tno\n')
            in_file.flush()

            args = arg_parser.parse_args([
                self.get_url('/cookie'),
                '--load-cookies', in_file.name,
                '--tries', '1',
                '--save-cookies', 'wpull_test_cookies.txt',
                '--keep-session-cookies',
            ])
            builder = Builder(args)

            with cd_tempdir():
                engine = builder.build()
                exit_code = yield engine()

                self.assertEqual(0, exit_code)
                self.assertEqual(1, builder.factory['Statistics'].files)

                cookies = list(builder.factory['CookieJar'])
                _logger.debug('{0}'.format(cookies))
                self.assertEqual(1, len(cookies))
                self.assertEqual('test', cookies[0].name)
                self.assertEqual('yes', cookies[0].value)

                with open('wpull_test_cookies.txt', 'rb') as saved_file:
                    cookie_data = saved_file.read()

                self.assertIn(b'test\tyes', cookie_data)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_diff_host(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args(
            [self.get_url('/redirect?where=diff-host')])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)


class TestAppBad(BadAppTestCase):
    def setUp(self):
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_cookie(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/bad_cookie'),
        ])
        builder = Builder(args)
        with cd_tempdir():
            engine = builder.build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        cookies = list(builder.factory['CookieJar'])
        _logger.debug('{0}'.format(cookies))
        self.assertEqual(2, len(cookies))
