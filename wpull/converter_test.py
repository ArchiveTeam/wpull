# encoding=utf-8
import os.path

from wpull.backport.testing import unittest
from wpull.converter import CSSConverter, HTMLConverter
from wpull.database import URLTable, Status
from wpull.writer import PathNamer


try:
    from tempfile import TemporaryDirectory
except ImportError:
    from wpull.backport.tempfile import TemporaryDirectory

CSS_TEXT = '''
body {
    background: url('http://example.com/image.png');
    background: url('http://example.com/cat.jpg');
}
/* ð £fbġ̉bbb */
'''
HTML_TEXT = '''
<html>
<head>
<style>
    background: url('http://example.com/image.png');
    background: url('http://example.com/cat.jpg');
</style>
<body>
    ¡¡ÐÉ§bh¾Í¿fg½½ËGFÐÅFÁ
    <a href="http://example.com/tubes.html">Series of tubes</a>
    <a href="http://example.com/lol.html">LOL Internet</a>
    <div style="background: url('http://example.com/fox.jpg');"></div>
    <div style="background: url('http://example.com/ferret.jpg');"></div>
</body>
</html>
'''


class TestConverter(unittest.TestCase):
    def test_css_converter(self):
        with TemporaryDirectory() as temp_dir:
            path_namer = PathNamer(temp_dir)
            url_table = URLTable()

            url_table.add([
                'http://example.com/styles.css',
                'http://example.com/image.png',
                'http://example.com/cat.jpg',
                'http://example.com/cat.jpg',
            ])
            url_table.update(
                'http://example.com/styles.css',
                status=Status.done,
                link_type='css'
            )
            url_table.update(
                'http://example.com/image.png',
                status=Status.done,
            )

            css_filename = os.path.join(temp_dir, 'styles.css')
            new_css_filename = os.path.join(temp_dir, 'styles.css-new')

            with open(css_filename, 'w') as out_file:
                out_file.write(CSS_TEXT)

            converter = CSSConverter(path_namer, url_table)

            converter.convert(
                css_filename, new_css_filename,
                base_url='http://example.com/styles.css'
            )

            with open(new_css_filename, 'r') as in_file:
                converted_text = in_file.read()

            self.assertIn("url('image.png')", converted_text)
            self.assertIn("url('http://example.com/cat.jpg')", converted_text)

    def test_html_converter(self):
        with TemporaryDirectory() as temp_dir:
            path_namer = PathNamer(temp_dir)
            url_table = URLTable()

            url_table.add([
                'http://example.com/styles.css',
                'http://example.com/image.png',
                'http://example.com/cat.jpg',
                'http://example.com/fox.jpg',
                'http://example.com/ferret.jpg',
                'http://example.com/tubes.html',
            ])
            url_table.update(
                'http://example.com/styles.css',
                status=Status.done,
                link_type='css'
            )
            url_table.update(
                'http://example.com/image.png',
                status=Status.done,
            )
            url_table.update(
                'http://example.com/tubes.html',
                status=Status.done,
            )
            url_table.update(
                'http://example.com/ferret.jpg',
                status=Status.done,
            )

            html_filename = os.path.join(temp_dir, 'index.html')
            new_html_filename = os.path.join(temp_dir, 'index.html-new')

            with open(html_filename, 'w') as out_file:
                out_file.write(HTML_TEXT)

            converter = HTMLConverter(path_namer, url_table)

            converter.convert(
                html_filename, new_html_filename,
                base_url='http://example.com/index.html'
            )

            with open(new_html_filename, 'r') as in_file:
                converted_text = in_file.read()

            self.assertIn("url('image.png')", converted_text)
            self.assertIn("url('http://example.com/cat.jpg')", converted_text)
            self.assertIn('"tubes.html"', converted_text)
            self.assertIn('"http://example.com/lol.html"', converted_text)
            self.assertIn("url('http://example.com/fox.jpg')", converted_text)
            self.assertIn("url('ferret.jpg')", converted_text)
