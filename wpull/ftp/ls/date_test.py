import unittest
import datetime
from wpull.ftp.ls.date import parse_datetime


def new_datetime(*args):
    return datetime.datetime(*args, tzinfo=datetime.timezone.utc)


class TestDate(unittest.TestCase):
    def test_parse_datetime(self):
        self.assertEqual(
            new_datetime(1990, 2, 9),
            parse_datetime('Feb  9 1990')[0]
        )

        self.assertEqual(
            new_datetime(2005, 2, 9, 18, 45),
            parse_datetime(
                'Feb  9  18:45',
                datetime_now=new_datetime(2005, 2, 9, 20, 0)
            )[0]
        )

        self.assertEqual(
            new_datetime(2004, 2, 9, 18, 45),
            parse_datetime(
                'Feb  9  18:45',
                datetime_now=new_datetime(2005, 2, 9, 17, 0)
            )[0]
        )

        self.assertEqual(
            new_datetime(2005, 2, 10),
            parse_datetime(
                'Feb 10 2005',
                datetime_now=new_datetime(2005, 2, 5)
            )[0]
        )

        self.assertEqual(
            new_datetime(2005, 2, 10),
            parse_datetime(
                'Feb 10 2005',
                datetime_now=new_datetime(2005, 2, 12)
            )[0]
        )

        self.assertEqual(
            new_datetime(2010, 5, 7),
            parse_datetime('2010-05-07')[0]
        )

        self.assertEqual(
            new_datetime(2010, 5, 7),
            parse_datetime('2010年5月7日')[0]
        )

        self.assertEqual(
            new_datetime(2010, 5, 7),
            parse_datetime('07-05-2010')[0]
        )

        self.assertEqual(
            new_datetime(2010, 5, 7),
            parse_datetime('07-05-2010')[0]
        )

        self.assertEqual(
            new_datetime(2014, 4, 1, 22, 39),
            parse_datetime('Apr 1 2014 10:39PM', is_day_period=True)[0]
        )
        self.assertEqual(
            new_datetime(2014, 4, 1, 12, 39),
            parse_datetime('Apr 1 2014 12:39PM', is_day_period=True)[0]
        )
        self.assertEqual(
            new_datetime(2014, 4, 1, 0, 39),
            parse_datetime('Apr 1 2014 12:39AM', is_day_period=True)[0]
        )

        # TODO: more tests
