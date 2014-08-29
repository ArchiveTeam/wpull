import unittest
from wpull.ftp.util import parse_address


class TestUtil(unittest.TestCase):
    def test_parse_address(self):
        self.assertEqual(
            ('127.0.0.1', 34805),
            parse_address('227 Now Entering Passive Mode (127,0,0,1,135,245)')
        )
        self.assertEqual(
            ('127.0.0.1', 254),
            parse_address('227 Passive Mode! (127, 000, 000, 001, 000, 254)')
        )
