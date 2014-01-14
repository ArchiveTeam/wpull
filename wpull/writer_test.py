# encoding=utf-8
import os.path
import tornado.testing
import unittest

from wpull.app import Builder
from wpull.app_test import cd_tempdir
from wpull.options import AppArgumentParser
from wpull.testing.goodapp import GoodAppTestCase
from wpull.writer import url_to_dir_path, url_to_filename


class TestWriter(unittest.TestCase):
    def test_writer_filename(self):
        url = 'http://../sométhing/'
        self.assertEqual(
            'http/%2E%2E/som%C3%A9thing/index.html',
            os.path.join(
                url_to_dir_path(
                    url, include_protocol=True, include_hostname=True),
                url_to_filename(url)
            )
        )


class TestWriterApp(GoodAppTestCase):
    @tornado.testing.gen_test
    def test_new_file_and_clobber(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt')])
        with cd_tempdir() as temp_dir:
            engine = Builder(args).build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            expected_filename = os.path.join(temp_dir, 'my_file.txt')

            self.assertTrue(os.path.exists(expected_filename))

            with open(expected_filename, 'rb') as in_file:
                self.assertIn(b'END', in_file.read())

            engine = Builder(args).build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            expected_filename = os.path.join(temp_dir, 'my_file.txt.1')

            self.assertTrue(os.path.exists(expected_filename))
