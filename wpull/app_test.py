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
    @tornado.testing.gen_test
    def test_one_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/')])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test(timeout=10)
    def test_many_page_with_some_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/blog/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(ExitStatus.server_error, exit_code)

    @tornado.testing.gen_test
    def test_app_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--warc-file', 'test',
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
        ])
        with cd_tempdir():
            engine = Builder(args).build()
            exit_code = yield engine()
        self.assertEqual(0, exit_code)
