import gzip
import os

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser
from wpull.testing.integration.base import FTPAppTestCase
import wpull.testing.async


class TestFTPApp(FTPAppTestCase):
    @wpull.testing.async.async_test()
    def test_basic(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_login(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/example (copy).txt'),
            '--user', 'smaug',
            '--password', 'gold1',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_login_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/example (copy).txt'),
            '--user', 'smaug',
            '--password', 'hunter2',
            '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(6, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            self.get_url('/no_exist'),
            '-r',
            '--no-remove-listing',
            '--level', '1',  # TODO: handle symlink loops
            '--tries', '1',
            '--wait', '0',
            '--no-host-directories',
            '--warc-file', 'mywarc',
            '--preserve-permissions',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(8, exit_code)
        self.assertEqual(6, builder.factory['Statistics'].files)

        print(os.listdir('.'))

        self.assertTrue(os.path.exists('.listing'))
        self.assertTrue(os.path.exists('example (copy).txt'))
        self.assertTrue(os.path.exists('readme.txt'))
        self.assertFalse(os.path.islink('readme.txt'))
        self.assertTrue(os.path.exists('example1/.listing'))
        self.assertTrue(os.path.exists('example2💎/.listing'))
        self.assertTrue(os.path.exists('mywarc.warc.gz'))

        with gzip.GzipFile('mywarc.warc.gz') as in_file:
            data = in_file.read()

            self.assertIn(b'FINISHED', data)
            self.assertIn('The real treasure is in Smaug’s heart 💗.\n'
                          .encode('utf-8'),
                          data)

    @wpull.testing.async.async_test()
    def test_retr_symlinks_off(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '-r',
            '--level', '1',
            '--tries', '1',
            '--no-host-directories',
            '--retr-symlinks=off',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

        print(os.listdir('.'))

        self.assertTrue(os.path.exists('example (copy).txt'))
        self.assertTrue(os.path.exists('readme.txt'))
        self.assertTrue(os.path.islink('readme.txt'))

    @wpull.testing.async.async_test()
    def test_file_vs_directory(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/example2💎'),
            '--no-host-directories',
            '--no-remove-listing',
            '-r',
            '-l=1',
            '--tries=1'
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()
        print(list(os.walk('.')))

        self.assertEqual(0, exit_code)
        self.assertTrue(os.path.exists('example2💎/.listing'))

    @wpull.testing.async.async_test()
    def test_invalid_char_dir_list(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/hidden/invalid_chars/'),
            '--no-host-directories',
            '--no-remove-listing',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()
        print(list(os.walk('.')))

        self.assertEqual(0, exit_code)
        self.assertTrue(os.path.exists('.listing'))

    @wpull.testing.async.async_test()
    def test_globbing(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/read*.txt'),
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()
        print(list(os.walk('.')))

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_no_globbing(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/read*.txt'),
            '--tries=1',
            '--no-glob',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()
        print(list(os.walk('.')))

        self.assertEqual(8, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test()
    def test_file_continue(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/example (copy).txt'),
                                      '--continue', '--debug'])

        filename = os.path.join(self.temp_dir.name, 'example (copy).txt')

        with open(filename, 'wb') as out_file:
            out_file.write(b'The')

        app = Builder(args, unit_test=True).build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

        with open(filename, 'rb') as in_file:
            data = in_file.read()

            self.assertEqual(
                'The real treasure is in Smaug’s heart 💗.\n'
                    .encode('utf-8'),
                data
            )
