# encoding=utf-8
import hashlib
import os.path
import tornado.testing
import unittest

from wpull.app import Builder
from wpull.app_test import cd_tempdir
from wpull.options import AppArgumentParser
from wpull.testing.goodapp import GoodAppTestCase
from wpull.writer import url_to_dir_path, url_to_filename, quote_filename


DEFAULT_TIMEOUT = 30


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

        filename = '%95%B6%8E%9A%89%BB%82%AF.html?'
        self.assertEqual(
            '%95%B6%8E%9A%89%BB%82%AF.html%3F',
            quote_filename(filename)
        )


class TestWriterApp(GoodAppTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
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

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt'),
            '--continue', '--debug'])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'my_file.txt')

            with open(filename, 'wb') as out_file:
                out_file.write(b'START')

            engine = Builder(args).build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                data = in_file.read()

                self.assertEqual('54388a281352fdb2cfa66009ac0e35dd8916af7c',
                    hashlib.sha1(data).hexdigest())

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_timestamping_hit(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/lastmod'),
            '--timestamping'
        ])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'lastmod')

            with open(filename, 'wb') as out_file:
                out_file.write(b'HI')

            os.utime(filename, (631152000, 631152000))

            builder = Builder(args)
            engine = builder.build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_timestamping_miss(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/lastmod'),
            '--timestamping'
        ])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'lastmod')

            with open(filename, 'wb') as out_file:
                out_file.write(b'HI')

            os.utime(filename, (636249600, 636249600))

            builder = Builder(args)
            engine = builder.build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HELLO', in_file.read())

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_timestamping_hit_orig(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/lastmod'),
            '--timestamping'
        ])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'lastmod')
            filename_orig = os.path.join(temp_dir, 'lastmod')

            with open(filename, 'wb') as out_file:
                out_file.write(b'HI')

            with open(filename_orig, 'wb') as out_file:
                out_file.write(b'HI')

            os.utime(filename_orig, (631152000, 631152000))

            builder = Builder(args)
            engine = builder.build()
            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())

            with open(filename_orig, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())
