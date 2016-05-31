import glob
import os
import re
import unittest

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser
from wpull.testing.integration.base import AppTestCase
import wpull.testing.async


class TestYoutubeDl(AppTestCase):
    @unittest.skip('not a good idea to test continuously on external servers')
    @wpull.testing.async.async_test()
    def test_youtube_dl(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            'https://www.youtube.com/watch?v=tPEE9ZwTmy0',
            '--warc-file', 'test',
            '--no-warc-compression',
            '--youtube-dl',
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)
        # TODO: proxy doesn't account for files yet
        # self.assertEqual(1, builder.factory['Statistics'].files)

        print(list(os.walk('.')))

        with open('test.warc', 'rb') as warc_file:
            data = warc_file.read()

            self.assertTrue(b'youtube-dl/' in data, 'include version')
            self.assertTrue(re.search(b'Fetched.*googlevideo\.com/videoplayback', data))
            self.assertTrue(b'WARC-Target-URI: metadata://www.youtube.com/watch?v=tPEE9ZwTmy0' in data)
            self.assertTrue(b'Content-Type: application/vnd.youtube-dl_formats+json' in data)

        video_files = tuple(glob.glob('*.mp4') + glob.glob('*.webm') + glob.glob('*.mkv'))
        self.assertTrue(video_files)

        annotations = tuple(glob.glob('*.annotation*'))
        self.assertTrue(annotations)

        info_json = tuple(glob.glob('*.info.json'))
        self.assertTrue(info_json)

        thumbnails = tuple(glob.glob('*.jpg'))
        self.assertTrue(thumbnails)

    @unittest.skip('not a good idea to test continuously on external servers')
    @wpull.testing.async.async_test()
    def test_propagate_ipv4_only_and_no_cert_check_to_youtube_dl(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            'https://www.youtube.com/watch?v=tPEE9ZwTmy0',
            '--warc-file', 'test',
            '--debug',  # to capture youtube-dl arguments in the log
            '--no-warc-compression',
            '--youtube-dl',
            '--inet4-only',
            '--no-check-certificate',
            '--output-file', 'test.log'
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

        with open('test.log', 'rb') as test_log:
            data = test_log.read()

            self.assertTrue(re.search(b'Starting process \[\'youtube-dl.*--force-ipv4', data))
            self.assertTrue(re.search(b'Starting process \[\'youtube-dl.*--no-check-certificate', data))

    @unittest.skip('not a good idea to test continuously on external servers')
    @wpull.testing.async.async_test()
    def test_youtube_dl_defaults_have_neither_ipv4_only_nor_no_cert_check(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            'https://www.youtube.com/watch?v=tPEE9ZwTmy0',
            '--warc-file', 'test',
            '--debug',
            '--no-warc-compression',
            '--youtube-dl',
            '--output-file', 'test.log'
        ])
        builder = Builder(args, unit_test=True)

        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

        with open('test.log', 'rb') as test_log:
            data = test_log.read()

            self.assertFalse(re.search(b'Starting process \[\'youtube-dl.*--force-ipv4', data))
            # XXX: --no-check-certificate required regardless since MITM proxy
            # uses invalid cert
            # self.assertFalse(re.search(b'Starting process \[\'youtube-dl.*--no-check-certificate', data))

