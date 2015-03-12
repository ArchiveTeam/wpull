import os
import unittest

from wpull.path import url_to_dir_parts, url_to_filename, safe_filename, \
    anti_clobber_dir_path, parse_content_disposition
from wpull.testing.util import TempDirMixin


class TestPath(unittest.TestCase, TempDirMixin):
    def setUp(self):
        self.set_up_temp_dir()

    def tearDown(self):
        self.tear_down_temp_dir()

    def test_url_to_dir_parts(self):
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

    def test_url_to_filename(self):
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

    def test_safe_filename(self):
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
        with self.cd_tempdir():
            self.assertEqual(
                'a',
                anti_clobber_dir_path('a')
            )

        with self.cd_tempdir():
            self.assertEqual(
                'a/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g/')
            )

        with self.cd_tempdir():
            self.assertEqual(
                'a/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with self.cd_tempdir():
            with open('a', 'w'):
                pass

            self.assertEqual(
                'a.d/b/c/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with self.cd_tempdir():
            os.makedirs('a/b')
            with open('a/b/c', 'w'):
                pass

            self.assertEqual(
                'a/b/c.d/d/e/f/g',
                anti_clobber_dir_path('a/b/c/d/e/f/g')
            )

        with self.cd_tempdir():
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
