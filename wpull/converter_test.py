# encoding=utf-8
import os.path

from wpull.app_test import cd_tempdir
from wpull.backport.testing import unittest
from wpull.converter import CSSConverter, HTMLConverter
from wpull.database import URLTable, Status


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
    <hr>
</body>
<!-- hello world!! -->
</html>
'''
XHTML_TEXT = '''
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
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
    <hr>
</body>
<!-- hello world!! -->
</html>
'''


class TestConverter(unittest.TestCase):
    def test_css_converter(self):
        with cd_tempdir() as temp_dir:
            url_table = URLTable()
            css_filename = os.path.join(temp_dir, 'styles.css')
            image_filename = os.path.join(temp_dir, 'image.png')
            new_css_filename = os.path.join(temp_dir, 'styles.css-new')

            url_table.add([
                'http://example.com/styles.css',
                'http://example.com/image.png',
                'http://example.com/cat.jpg',
                'http://example.com/cat.jpg',
            ])
            url_table.update(
                'http://example.com/styles.css',
                status=Status.done,
                link_type='css',
                filename=os.path.relpath(css_filename, temp_dir)
            )
            url_table.update(
                'http://example.com/image.png',
                status=Status.done,
                filename=os.path.relpath(image_filename, temp_dir)
            )

            with open(css_filename, 'w') as out_file:
                out_file.write(CSS_TEXT)

            with open(image_filename, 'wb'):
                pass

            converter = CSSConverter(url_table)

            converter.convert(
                css_filename, new_css_filename,
                base_url='http://example.com/styles.css'
            )

            with open(new_css_filename, 'r') as in_file:
                converted_text = in_file.read()

            self.assertIn("url('image.png')", converted_text)
            self.assertIn("url('http://example.com/cat.jpg')", converted_text)

    def test_html_converter(self):
        with cd_tempdir() as temp_dir:
            url_table = URLTable()

            image_filename = os.path.join(temp_dir, 'image.png')
            tubes_filename = os.path.join(temp_dir, 'tubes.html')
            ferret_filename = os.path.join(temp_dir, 'ferret.jpg')

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
                filename=os.path.relpath(image_filename, temp_dir)
            )
            url_table.update(
                'http://example.com/tubes.html',
                status=Status.done,
                filename=os.path.relpath(tubes_filename, temp_dir)
            )
            url_table.update(
                'http://example.com/ferret.jpg',
                status=Status.done,
                filename=os.path.relpath(ferret_filename, temp_dir)
            )

            html_filename = os.path.join(temp_dir, 'index.html')
            new_html_filename = os.path.join(temp_dir, 'index.html-new')

            with open(html_filename, 'w') as out_file:
                out_file.write(HTML_TEXT)

            for filename in [image_filename, tubes_filename, ferret_filename]:
                with open(filename, 'wb'):
                    pass

            converter = HTMLConverter(url_table)

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
            self.assertIn("hello world!!", converted_text)
            self.assertIn("<hr>", converted_text)

    def test_xhtml_converter(self):
        with cd_tempdir() as temp_dir:
            url_table = URLTable()

            image_filename = os.path.join(temp_dir, 'image.png')
            tubes_filename = os.path.join(temp_dir, 'tubes.html')
            ferret_filename = os.path.join(temp_dir, 'ferret.jpg')

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
                filename=os.path.relpath(image_filename, temp_dir)
            )
            url_table.update(
                'http://example.com/tubes.html',
                status=Status.done,
                filename=os.path.relpath(tubes_filename, temp_dir)
            )
            url_table.update(
                'http://example.com/ferret.jpg',
                status=Status.done,
                filename=os.path.relpath(ferret_filename, temp_dir)
            )

            html_filename = os.path.join(temp_dir, 'index.html')
            new_html_filename = os.path.join(temp_dir, 'index.html-new')

            with open(html_filename, 'w') as out_file:
                out_file.write(XHTML_TEXT)

            for filename in [image_filename, tubes_filename, ferret_filename]:
                with open(filename, 'wb'):
                    pass

            converter = HTMLConverter(url_table)

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
            self.assertIn("hello world!!", converted_text)
            self.assertIn("<hr/>", converted_text)
