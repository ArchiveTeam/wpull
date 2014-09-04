import unittest
from wpull.ftp.ls.parse import ListingParser


UNIX_LS = '''-rw-r--r--   1 root     other        531 Jan 29 03:26 README
dr-xr-xr-x   2 root     other        512 Apr  8  1994 etc
dr-xr-xr-x   2 root     512 Apr  8  1994 etc
lrwxrwxrwx   1 root     other          7 Jan 25 00:17 bin -> usr/bin
'''

MSDOS_LS = '''04-27-00  09:09PM       <DIR>          licensed
07-18-00  10:16AM       <DIR>          pub
04-14-00  03:47PM                  589 readme.htm
'''


class TestParse(unittest.TestCase):
    def test_parse_unix(self):
        # TODO: check values
        parser = ListingParser(UNIX_LS)
        parser.run_heuristics()
        print(parser.parse())

    def test_parse_msdos(self):
        # TODO: check values
        parser = ListingParser(MSDOS_LS)
        parser.run_heuristics()
        print(parser.parse())
