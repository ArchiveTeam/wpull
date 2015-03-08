import unittest

from wpull.processor.ftp import to_dir_path_url, append_slash_to_path_url
from wpull.url import URLInfo


class TestFTP(unittest.TestCase):
    def test_to_dir_path_url(self):
        self.assertEqual(
            'ftp://putfile.com/',
            to_dir_path_url(URLInfo.parse('ftp://putfile.com/'))
        )
        self.assertEqual(
            'ftp://putfile.com/',
            to_dir_path_url(URLInfo.parse('ftp://putfile.com/asdf'))
        )
        self.assertEqual(
            'ftp://putfile.com/asdf/',
            to_dir_path_url(URLInfo.parse('ftp://putfile.com/asdf/qwer'))
        )

    def test_append_slash_to_path_url(self):
        self.assertEqual(
            'ftp://putfile.com/example/',
            append_slash_to_path_url(
                URLInfo.parse('ftp://putfile.com/example')
            )
        )
