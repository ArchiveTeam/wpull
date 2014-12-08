import unittest

from wpull.ftp.ls.listing import guess_listing_type


UNIX_LS = '''-rw-r--r--   1 root     other        531 Jan 29 03:26 README
dr-xr-xr-x   2 root     other        512 Apr  8  1994 etc
dr-xr-xr-x   2 root     512 Apr  8  1994 etc
lrwxrwxrwx   1 root     other          7 Jan 25 00:17 bin -> usr/bin
'''

MSDOS_LS = '''04-27-00  09:09PM       <DIR>          licensed
07-18-00  10:16AM       <DIR>          pub
04-14-00  03:47PM                  589 readme.htm
'''


MSDOS_NO_DIR_LS = '''04-27-00  09:09PM               123  licensed.exe
07-18-00  10:16AM               456  pub.pdf
04-14-00  03:47PM                  589 readme.htm
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


class TestHeuristic(unittest.TestCase):
    def test_guess_listing_type(self):
        self.assertEqual('unix', guess_listing_type(UNIX_LS.splitlines()))
        self.assertEqual('msdos', guess_listing_type(MSDOS_LS.splitlines()))
        self.assertEqual('msdos', guess_listing_type(MSDOS_NO_DIR_LS.splitlines()))
        self.assertEqual('nlst', guess_listing_type(NLST_LS.splitlines()))
        self.assertEqual('unknown', guess_listing_type(MVS_LS.splitlines()))
