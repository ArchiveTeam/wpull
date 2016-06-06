import datetime
import unittest

import functools

from wpull.protocol.ftp.ls.listing import guess_listing_type, parse_unix_perm, \
    ListingParser, FileEntry, UnknownListingError

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

MSDOS_NO_DIR_LS = '''04-27-00  09:09PM               123  licensed.exe
07-18-00  10:16AM               456  pub.pdf
04-14-00  03:47PM                  589 readme.htm
'''

UNIX_LS_DATELIKE_FILE = '''-rw-r--r--    1 500      500       1558532 Dec 30  2009 2009-12
-rw-r--r--    1 500      500      10564020 Jan 14  2010 2010-01
'''

UNIX_LS_DATELIKE_FILE_2 = '''-rw-r--r--    1 1000     100        242408 Mar 24  2010 english_german.2010-03-24.tar.gz
drwxr-xr-x    2 1000     100          4096 Mar 24  2010 old
'''

NLST_LS = '''horse.txt
fish
dolphin.jpg
delicious cake.wri
egg
'''

MVS_LS = '''  WYOSPT 3420   2003/05/21  1  200  FB      80  8053  PS  48-MVS.FILE
  WPTA01 3290   2004/03/04  1    3  FB      80  3125  PO  49-MVS.DATASET
  TSO004 3390   VSAM 50-mvs-file
  TSO005 3390   2005/06/06 213000 U 0 27998 PO 51-mvs-dir
  NRP004 3390   **NONE**    1   15  NONE     0     0  PO  52-MVS-NONEDATE.DATASET
'''



class TestListing(unittest.TestCase):
    def test_guess_listing_type(self):
        self.assertEqual('unix', guess_listing_type(UNIX_LS.splitlines()))
        self.assertEqual('msdos', guess_listing_type(MSDOS_LS.splitlines()))
        self.assertEqual('msdos', guess_listing_type(MSDOS_NO_DIR_LS.splitlines()))
        self.assertEqual('nlst', guess_listing_type(NLST_LS.splitlines()))
        self.assertEqual('unknown', guess_listing_type(MVS_LS.splitlines()))

    def test_parse_unix_perm(self):
        self.assertEqual(0, parse_unix_perm('a'))
        self.assertEqual(0, parse_unix_perm('1234567890'))
        self.assertEqual(0, parse_unix_perm('---------'))
        self.assertEqual(0o400, parse_unix_perm('r--------'))
        self.assertEqual(0o040, parse_unix_perm('---r-----'))
        self.assertEqual(0o004, parse_unix_perm('------r--'))
        self.assertEqual(0o444, parse_unix_perm('r--r--r--'))
        self.assertEqual(0o222, parse_unix_perm('-w--w--w-'))
        self.assertEqual(0o111, parse_unix_perm('--x--x--x'))
        self.assertEqual(0o111, parse_unix_perm('--s--s--s'))
        self.assertEqual(0o545, parse_unix_perm('r-xr--r-x'))
        self.assertEqual(0o632, parse_unix_perm('rw--wx-w-'))
        self.assertEqual(0o535, parse_unix_perm('r-x-wxr-x'))
        self.assertEqual(0o777, parse_unix_perm('rwxrwxrwx'))
        self.assertEqual(0o777, parse_unix_perm('rwsrwsrws'))

    def test_parse_unix(self):
        parser = ListingParser(UNIX_LS)
        results = list(parser.parse_input())
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        datetime_now = datetime.datetime.utcnow()
        datetime_now = datetime_now.replace(tzinfo=datetime.timezone.utc)
        current_year = datetime_now.year

        datetime_1 = date_factory(current_year, 1, 29, 3, 26)
        datetime_2 = date_factory(current_year, 1, 25, 0, 17)

        if datetime_1 > datetime_now:
            datetime_1 = datetime_1.replace(year=current_year - 1)

        if datetime_2 > datetime_now:
            datetime_2 = datetime_2.replace(year=current_year - 1)

        self.assertEqual(
            [
                FileEntry('README', 'file', 531,
                          datetime_1,
                          perm=0o644),
                FileEntry('etc', 'dir', 512,
                          date_factory(1994, 4, 8),
                          perm=0o555),
                FileEntry('etc', 'dir', 512,
                          date_factory(1994, 4, 8),
                          perm=0o555),
                FileEntry('bin', 'symlink', 7,
                          datetime_2,
                          'usr/bin', perm=0o777),
                FileEntry('blah', 'dir', 512,
                          date_factory(2004, 4, 8),
                          perm=0o555),
            ],
            results
        )

    def test_parse_msdos(self):
        parser = ListingParser(MSDOS_LS)
        results = list(parser.parse_input())
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
        results = list(parser.parse_input())
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('licensed.exe', 'file', 123,
                          date_factory(2000, 4, 27, 21, 9)),
                FileEntry('pub.pdf', 'file', 456,
                          date_factory(2000, 7, 18, 10, 16)),
                FileEntry('readme.htm', 'file', 589,
                          date_factory(2000, 4, 14, 15, 47)),
            ],
            results
        )

    def test_parse_nlst(self):
        parser = ListingParser(NLST_LS)
        results = list(parser.parse_input())

        self.assertEqual(
            [
                FileEntry('horse.txt'),
                FileEntry('fish'),
                FileEntry('dolphin.jpg'),
                FileEntry('delicious cake.wri'),
                FileEntry('egg'),
            ],
            results
        )

    def test_parse_junk(self):
        parser = ListingParser(' aj  \x00     a304 jrf')

        self.assertRaises(UnknownListingError, parser.parse_input)

    def test_parse_unix_datelike_file(self):
        parser = ListingParser(UNIX_LS_DATELIKE_FILE)
        results = list(parser.parse_input())
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('2009-12', 'file', 1558532,
                          date_factory(2009, 12, 30),
                          perm=0o644),
                FileEntry('2010-01', 'file', 10564020,
                          date_factory(2010, 1, 14),
                          perm=0o644),
            ],
            results
        )

    def test_parse_unix_datelike_file_2(self):
        parser = ListingParser(UNIX_LS_DATELIKE_FILE_2)
        results = list(parser.parse_input())
        date_factory = functools.partial(datetime.datetime,
                                         tzinfo=datetime.timezone.utc)

        self.assertEqual(
            [
                FileEntry('english_german.2010-03-24.tar.gz', 'file', 242408,
                          date_factory(2010, 3, 24),
                          perm=0o644),
                FileEntry('old', 'dir', 4096,
                          date_factory(2010, 3, 24),
                          perm=0o755),
            ],
            results
        )
