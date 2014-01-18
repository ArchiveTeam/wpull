# encoding=utf-8
import contextlib
import os
import tornado.testing

from wpull.app import Builder
from wpull.errors import ExitStatus
from wpull.options import AppArgumentParser
from wpull.testing.goodapp import GoodAppTestCase


try:
    from tempfile import TemporaryDirectory
except ImportError:
    from wpull.backport.tempfile import TemporaryDirectory


DEFAULT_TIMEOUT = 30


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
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_one_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/')])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)

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
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(ExitStatus.server_error, exit_code)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--database', 'test.db',
            '--server-response',
            '--random-wait',
            '--wait', '0.1',
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
