import contextlib
import os
import tempfile
import tornado.testing

from wpull.app import Builder
from wpull.errors import ExitStatus
from wpull.options import AppArgumentParser
from wpull.testing.goodapp import GoodAppTestCase


@contextlib.contextmanager
def cd_tempdir():
    original_dir = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield
        finally:
            os.chdir(original_dir)


class TestApp(GoodAppTestCase):
    @tornado.testing.gen_test
    def test_one_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/')])
        engine = Builder(args).build()
        with cd_tempdir():
            exit_code = yield engine()
        self.assertEqual(0, exit_code)

    @tornado.testing.gen_test
    def test_many_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/blog/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
        ])
        engine = Builder(args).build()
        with cd_tempdir():
            exit_code = yield engine()
        self.assertEqual(ExitStatus.server_error, exit_code)
