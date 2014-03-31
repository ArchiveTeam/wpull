# encoding=utf-8
import hashlib
import os.path
import tornado.testing
import unittest

from wpull.app import Builder
from wpull.app_test import cd_tempdir
from wpull.options import AppArgumentParser
from wpull.testing.goodapp import GoodAppTestCase
from wpull.writer import (url_to_dir_parts, url_to_filename, safe_filename,
    anti_clobber_dir_path)


DEFAULT_TIMEOUT = 30


class TestWriter(unittest.TestCase):
    def test_writer_path_dir(self):
        self.assertEqual(
            ['blog'],
            url_to_dir_parts('http://example.com/blog/')
        )
        self.assertEqual(
            ['blog'],
            url_to_dir_parts('http://example.com/blog/image.png')
        )
        self.assertEqual(
            ['example.com', 'blog'],
            url_to_dir_parts(
                'http://example.com/blog/image.png', include_hostname=True
            )
        )
        self.assertEqual(
            [],
            url_to_dir_parts('http://example.com/')
        )
        self.assertEqual(
            ['example.com:123'],
            url_to_dir_parts(
                'http://example.com:123/',
                include_hostname=True, alt_char=False,
            )
        )
        self.assertEqual(
            ['example.com+123'],
            url_to_dir_parts(
                'http://example.com:123/',
                include_hostname=True, alt_char=True,
            )
        )

    def test_writer_filename(self):
        self.assertEqual(
            'image.png',
            url_to_filename('http://example.com/blog/image.png')
        )
        self.assertEqual(
            'index.html',
            url_to_filename('http://example.com/blog/')
        )
        self.assertEqual(
            'index.html',
            url_to_filename('http://example.com/')
        )
        self.assertEqual(
            'index.html?blah=',
            url_to_filename('http://example.com/?blah=')
        )
        self.assertEqual(
            'index.html@blah=',
            url_to_filename('http://example.com/?blah=', alt_char=True)
        )

    def test_writer_safe_filename(self):
        self.assertEqual(
            'asdf',
            safe_filename(
                'asdf',
                os_type='unix', no_control=True, ascii_only=True, case=None
            )
        )
        self.assertEqual(
            'asdf%00',
            safe_filename(
                'asdf\x00',
                os_type='unix', no_control=True, ascii_only=True, case=None
            )
        )
        self.assertEqual(
            'asdf%3a',
            safe_filename(
                'Asdf:',
                os_type='windows', no_control=True, ascii_only=True,
                case='lower'
            )
        )
        self.assertEqual(
            'A%C3%A9',
            safe_filename(
                'aé',
                os_type='windows', no_control=True, ascii_only=True,
                case='upper',
            )
        )
        self.assertEqual(
            '%C3%A1bcdefgf29053e2',
            safe_filename(
                'ábcdefghij123456789012345678901234567890',
                max_length=20,
            )
        )

    def test_anti_clobber_dir_path(self):
        with cd_tempdir():
            self.assertEqual(
                'a',
                anti_clobber_dir_path('a')
            )

        with cd_tempdir():
            self.assertEqual(
                'a/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g/')
            )

        with cd_tempdir():
            self.assertEqual(
                'a/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with cd_tempdir():
            with open('a', 'w'):
                pass

            self.assertEqual(
                'a.d/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with cd_tempdir():
            os.makedirs('a/b')
            with open('a/b/c', 'w'):
                pass

            self.assertEqual(
                'a/b/c.d/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with cd_tempdir():
            os.makedirs('a/b/c/d/e/f')
            with open('a/b/c/d/e/f/g', 'w'):
                pass

            self.assertEqual(
                'a/b/c/d/e/f/g.d',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
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

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_dir_or_file(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            args = arg_parser.parse_args([
                self.get_url('/dir_or_file'),
                '--recursive',
                '--no-host-directories',
            ])
            engine = Builder(args).build()

            os.mkdir('dir_or_file')

            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))
            self.assertTrue(os.path.isdir('dir_or_file'))
            self.assertTrue(os.path.isfile('dir_or_file.f'))

        with cd_tempdir():
            args = arg_parser.parse_args([
                self.get_url('/dir_or_file/'),
                '--recursive',
                '--no-host-directories',
            ])
            engine = Builder(args).build()

            with open('dir_or_file', 'wb'):
                pass

            exit_code = yield engine()

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))
            self.assertTrue(os.path.isdir('dir_or_file.d'))
            self.assertTrue(os.path.isfile('dir_or_file.d/index.html'))
            self.assertTrue(os.path.isfile('dir_or_file'))
