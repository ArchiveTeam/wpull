import datetime
import functools
import unittest

from wpull.ftp.ls.listing import FileEntry, UnknownListingError
from wpull.ftp.ls.parse import ListingParser


UNIX_LS = '''-rw-r--r--   1 root     other        531 Jan 29 03:26 README
dr-xr-xr-x   2 root     other        512 Apr  8  1994 etc
dr-xr-xr-x   2 root     512 Apr  8  1994 etc
lrwxrwxrwx   1 root     other          7 Jan 25 00:17 bin -> usr/bin
dr-xr-xr-x   2 root  other 512 Apr  8  2004 blah
'''

MSDOS_LS = '''04-27-00  09:09PM       <DIR>          licensed
07-18-00  10:16AM       <DIR>          pub
04-14-00  03:47PM                  589 readme.htm
'''

MSDOS_NO_DIR_LS = '''04-14-00  03:47PM                  589 readme.htm
'''

NLST = '''dog.txt
cat.txt
bird.txt
fish.txt
'''

UNIX_LS_DATELIKE_FILE = '''-rw-r--r--    1 500      500       1558532 Dec 30  2009 2009-12
-rw-r--r--    1 500      500      10564020 Jan 14  2010 2010-01
'''


class TestParse(unittest.TestCase):
    def test_parse_unix(self):
        parser = ListingParser(UNIX_LS)
        parser.run_heuristics()
        results = parser.parse()
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        current_year = datetime.datetime.utcnow().year
        self.assertEqual(
            [
                FileEntry('README', 'file', 531,
                          date_factory(current_year, 1, 29, 3, 26)),
                FileEntry('etc', 'dir', 512,
                          date_factory(1994, 4, 8)),
                FileEntry('etc', 'dir', 512,
                          date_factory(1994, 4, 8)),
                FileEntry('bin', 'other', 7,
                          date_factory(current_year, 1, 25, 0, 17)),
                FileEntry('blah', 'dir', 512,
                          date_factory(2004, 4, 8)),
            ],
            results
        )

    def test_parse_msdos(self):
        parser = ListingParser(MSDOS_LS)
        parser.run_heuristics()
        results = parser.parse()
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('licensed', 'dir', None,
                          date_factory(2000, 4, 27, 21, 9)),
                FileEntry('pub', 'dir', None,
                          date_factory(2000, 7, 18, 10, 16)),
                FileEntry('readme.htm', 'file', 589,
                          date_factory(2000, 4, 14, 15, 47)),
            ],
            results
        )

    def test_parse_msdos_no_dir(self):
        parser = ListingParser(MSDOS_NO_DIR_LS)
        parser.run_heuristics()
        results = parser.parse()
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('readme.htm', 'file', 589,
                          date_factory(2000, 4, 14, 15, 47)),
            ],
            results
        )

    def test_parse_nlst(self):
        parser = ListingParser(NLST)
        parser.run_heuristics()
        results = parser.parse()

        self.assertEqual(
            [
                FileEntry('dog.txt', None, None, None),
                FileEntry('cat.txt', None, None, None),
                FileEntry('bird.txt', None, None, None),
                FileEntry('fish.txt', None, None, None),
            ],
            results
        )

    def test_parse_junk(self):
        parser = ListingParser(' aj  \x00     a304 jrf')
        parser.run_heuristics()

        self.assertRaises(UnknownListingError, parser.parse)

    def test_parse_unix_datelike_file(self):
        parser = ListingParser(UNIX_LS_DATELIKE_FILE)
        parser.run_heuristics()
        results = parser.parse()
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('2009-12', 'file', 1558532,
                          date_factory(2009, 12, 30)),
                FileEntry('2010-01', 'file', 10564020,
                          date_factory(2010, 1, 14)),
            ],
            results
        )
