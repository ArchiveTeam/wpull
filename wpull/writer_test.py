# encoding=utf-8
import hashlib
import os.path
import unittest

from trollius import From

from wpull.app_test import cd_tempdir
from wpull.builder import Builder
from wpull.options import AppArgumentParser
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase
from wpull.testing.goodapp import GoodAppTestCase
from wpull.writer import (url_to_dir_parts, url_to_filename, safe_filename,
                          anti_clobber_dir_path, parse_content_disposition)


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

    def test_parse_content_disposition(self):
        self.assertEqual(
            'hello.txt',
            parse_content_disposition('attachment; filename=hello.txt')
        )
        self.assertEqual(
            'hello.txt',
            parse_content_disposition(
                'attachment; filename=hello.txt; filename*=blahblah')
        )
        self.assertEqual(
            'hello.txt',
            parse_content_disposition(
                'attachment; filename=hello.txt ;filename*=blahblah')
        )
        self.assertEqual(
            'hello.txt',
            parse_content_disposition('attachment; filename="hello.txt"')
        )
        self.assertEqual(
            'hello.txt',
            parse_content_disposition('attachment; filename="hello.txt" ;')
        )
        self.assertEqual(
            'hello world',
            parse_content_disposition('attachment; filename="hello world"')
        )
        self.assertEqual(
            'hello world',
            parse_content_disposition('attachment; filename="hello world"')
        )
        self.assertEqual(
            'hello world',
            parse_content_disposition("attachment; filename='hello world'")
        )
        self.assertEqual(
            'hello"world',
            parse_content_disposition('attachment; filename="hello\\"world"')
        )
        self.assertEqual(
            '\'hello"world\'',
            parse_content_disposition('attachment; filename="\'hello\\"world\'"')
        )
        self.assertEqual(
            '\'hello"world\'',
            parse_content_disposition(
                'attachment; filename="\'hello\\"world\'";')
        )
        self.assertFalse(
            parse_content_disposition('attachment; filename=')
        )
        self.assertFalse(
            parse_content_disposition('attachment; filename=""')
        )
        self.assertFalse(
            parse_content_disposition('attachment; filename=";')
        )
        self.assertFalse(
            parse_content_disposition('attachment; filename=\'aaa')
        )
        self.assertFalse(
            parse_content_disposition('attachment; filename="aaa')
        )


class TestWriterApp(GoodAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_new_file_and_clobber(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt')])

        with cd_tempdir() as temp_dir:
            app = Builder(args, unit_test=True).build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            expected_filename = os.path.join(temp_dir, 'my_file.txt')

            self.assertTrue(os.path.exists(expected_filename))

            with open(expected_filename, 'rb') as in_file:
                self.assertIn(b'END', in_file.read())

            app = Builder(args, unit_test=True).build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            expected_filename = os.path.join(temp_dir, 'my_file.txt.1')

            self.assertTrue(os.path.exists(expected_filename))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt'),
                                      '--continue', '--debug'])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'my_file.txt')

            with open(filename, 'wb') as out_file:
                out_file.write(b'START')

            app = Builder(args, unit_test=True).build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                data = in_file.read()

                self.assertEqual('54388a281352fdb2cfa66009ac0e35dd8916af7c',
                                 hashlib.sha1(data).hexdigest())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
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

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
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

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HELLO', in_file.read())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
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

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())

            with open(filename_orig, 'rb') as in_file:
                self.assertEqual(b'HI', in_file.read())

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_dir_or_file(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            args = arg_parser.parse_args([
                self.get_url('/dir_or_file'),
                '--recursive',
                '--no-host-directories',
            ])
            app = Builder(args, unit_test=True).build()

            os.mkdir('dir_or_file')

            exit_code = yield From(app.run())

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
            app = Builder(args, unit_test=True).build()

            with open('dir_or_file', 'wb'):
                pass

            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))
            self.assertTrue(os.path.isdir('dir_or_file.d'))
            self.assertTrue(os.path.isfile('dir_or_file.d/index.html'))
            self.assertTrue(os.path.isfile('dir_or_file'))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_adjust_extension(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/mordor'),
            self.get_url('/mordor?ring.asp'),
            self.get_url('/mordor?ring.htm'),
            self.get_url('/static/my_file.txt'),
            self.get_url('/static/style.css'),
            self.get_url('/static/style.css?hamster.exe'),
            self.get_url('/static/mojibake.html'),
            self.get_url('/static/mojibake.html?dolphin.png'),
            '--adjust-extension',
            '--no-host-directories',
        ])

        with cd_tempdir() as temp_dir:
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))

            self.assertTrue(os.path.isfile('mordor.html'))
            self.assertTrue(os.path.isfile('mordor?ring.asp.html'))
            self.assertTrue(os.path.isfile('mordor?ring.htm'))
            self.assertTrue(os.path.isfile('static/my_file.txt'))
            self.assertTrue(os.path.isfile('static/style.css'))
            self.assertTrue(os.path.isfile('static/style.css?hamster.exe.css'))
            self.assertTrue(os.path.isfile('static/mojibake.html'))
            self.assertTrue(os.path.isfile('static/mojibake.html?dolphin.png.html'))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_content_disposition(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/content_disposition?filename=hello1.txt'),
            self.get_url('/content_disposition?filename=hello2.txt;'),
            self.get_url('/content_disposition?filename="hello3.txt"'),
            self.get_url('/content_disposition?filename=\'hello4.txt\''),
            '--content-disposition',
            '--no-host-directories',
        ])

        with cd_tempdir() as temp_dir:
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))

            self.assertTrue(os.path.isfile('hello1.txt'))
            self.assertTrue(os.path.isfile('hello2.txt'))
            self.assertTrue(os.path.isfile('hello3.txt'))
            self.assertTrue(os.path.isfile('hello4.txt'))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_trust_server_names(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/redirect'),
            '--trust-server-names',
            '--no-host-directories',
            ])

        with cd_tempdir() as temp_dir:
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            print(list(os.walk('.')))

            self.assertTrue(os.path.isfile('index.html'))


class TestWriterFTPApp(FTPTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/example.txt'),
                                      '--continue', '--debug'])

        with cd_tempdir() as temp_dir:
            filename = os.path.join(temp_dir, 'example.txt')

            with open(filename, 'wb') as out_file:
                out_file.write(b'The')

            app = Builder(args, unit_test=True).build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)

            with open(filename, 'rb') as in_file:
                data = in_file.read()

                self.assertEqual(
                    'The real treasure is in Smaug’s heart 💗.\n'
                    .encode('utf-8'),
                    data
                )
