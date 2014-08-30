import datetime
import textwrap
import unittest

from wpull.ftp.util import parse_address, reply_code_tuple, \
    parse_machine_listing


SAMPLE_LISTING_1 = textwrap.dedent('''\
    Type=cdir;Modify=19981107085215;Perm=el; tmp
    Type=cdir;Modify=19981107085215;Perm=el; /tmp
    Type=pdir;Modify=19990112030508;Perm=el; ..
    Type=file;Size=25730;Modify=19940728095854;Perm=; capmux.tar.z
''')


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

    def test_reply_code_tuple(self):
        self.assertEqual((1, 2, 3), reply_code_tuple(123))
        self.assertEqual((5, 0, 1), reply_code_tuple(501))
        self.assertEqual((0, 0, 1), reply_code_tuple(1))

    def test_parse_machine_listing(self):
        results = parse_machine_listing(SAMPLE_LISTING_1)
        self.assertEqual(
            {
                'type': 'cdir',
                'modify': datetime.datetime(1998, 11, 7, 8, 52, 15,
                                            tzinfo=datetime.timezone.utc),
                'perm': 'el',
                'name': 'tmp'
            },
            results[0]
        )
        self.assertEqual(
            {
                'type': 'cdir',
                'modify': datetime.datetime(1998, 11, 7, 8, 52, 15,
                                            tzinfo=datetime.timezone.utc),
                'perm': 'el',
                'name': '/tmp'
            },
            results[1]
        )
        self.assertEqual(
            {
                'type': 'pdir',
                'modify': datetime.datetime(1999, 1, 12, 3, 5, 8,
                                            tzinfo=datetime.timezone.utc),
                'perm': 'el',
                'name': '..'
            },
            results[2]
        )
        self.assertEqual(
            {
                'type': 'file',
                'size': 25730,
                'modify': datetime.datetime(1994, 7, 28, 9, 58, 54,
                                            tzinfo=datetime.timezone.utc),
                'perm': '', 'name': 'capmux.tar.z'
            },
            results[3]
        )
        self.assertEqual(
            {
                'type': 'file',
                'name': 'myfile.txt'
            },
            parse_machine_listing('TYPE=file; myfile.txt')[0]
        )
        self.assertRaises(
            ValueError,
            parse_machine_listing,
            'modify=123413010204; myfile.txt'
        )
        self.assertRaises(
            ValueError,
            parse_machine_listing,
            'size=horse; myfile.txt'
        )
        self.assertRaises(
            ValueError,
            parse_machine_listing,
            'size=123;perm=asdf;myfile.txt'
        )
        self.assertRaises(
            ValueError,
            parse_machine_listing,
            'size=123;perm=asdf'
        )
