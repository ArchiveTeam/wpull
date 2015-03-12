# encoding=utf-8
import hashlib
import os.path
import unittest

from trollius import From

from wpull.builder import Builder
from wpull.options import AppArgumentParser
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase
from wpull.testing.goodapp import GoodAppTestCase
from wpull.testing.util import TempDirMixin


DEFAULT_TIMEOUT = 30


class TestWriterApp(GoodAppTestCase, TempDirMixin):
    def setUp(self):
        super().setUp()
        self.set_up_temp_dir()

    def tearDown(self):
        super().tearDown()
        self.tear_down_temp_dir()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_new_file_and_clobber(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt')])

        app = Builder(args, unit_test=True).build()
        exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)

        expected_filename = os.path.join(self.temp_dir.name, 'my_file.txt')

        self.assertTrue(os.path.exists(expected_filename))

        with open(expected_filename, 'rb') as in_file:
            self.assertIn(b'END', in_file.read())

        app = Builder(args, unit_test=True).build()
        exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)

        expected_filename = os.path.join(self.temp_dir.name, 'my_file.txt.1')

        self.assertTrue(os.path.exists(expected_filename))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/static/my_file.txt'),
                                      '--continue', '--debug'])

        filename = os.path.join(self.temp_dir.name, 'my_file.txt')

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

        filename = os.path.join(self.temp_dir.name, 'lastmod')

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

        filename = os.path.join(self.temp_dir.name, 'lastmod')

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

        filename = os.path.join(self.temp_dir.name, 'lastmod')
        filename_orig = os.path.join(self.temp_dir.name, 'lastmod')

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
    def test_dir_or_file_dir_got_first(self):
        arg_parser = AppArgumentParser()

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

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_dir_or_file_file_got_first(self):
        arg_parser = AppArgumentParser()

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

        builder = Builder(args, unit_test=True)
        app = builder.build()
        exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)

        print(list(os.walk('.')))

        self.assertTrue(os.path.isfile('index.html'))


class TestWriterFTPApp(FTPTestCase, TempDirMixin):
    def setUp(self):
        super().setUp()
        self.set_up_temp_dir()

    def tearDown(self):
        super().tearDown()
        self.tear_down_temp_dir()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/example (copy).txt'),
                                      '--continue', '--debug'])

        filename = os.path.join(self.temp_dir.name, 'example (copy).txt')

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
