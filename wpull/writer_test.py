# encoding=utf-8
import os.path
import unittest

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
