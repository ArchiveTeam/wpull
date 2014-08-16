# encoding=utf-8
import unittest

from wpull.body import Body


class TestBody(unittest.TestCase):
    def test_body(self):
        body = Body()
        body.write(b'abc')
        body.seek(0)

        self.assertEqual(3, body.size())
        self.assertEqual(b'abc', body.content())

        info = body.to_dict()

        self.assertEqual(3, info['length'])
        self.assertEqual(3, info['content_size'])
