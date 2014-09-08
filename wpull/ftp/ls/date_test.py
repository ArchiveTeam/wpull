import unittest
import datetime
from wpull.ftp.ls.date import parse_datetime


class TestDate(unittest.TestCase):
    def test_parse_datetime(self):
        datetime_now = datetime.datetime.utcnow()

        self.assertEqual(
            datetime.datetime(1990, 2, 9, tzinfo=datetime.timezone.utc),
            parse_datetime('Feb  9 1990')[0]
        )

        self.assertEqual(
            datetime.datetime(
                datetime_now.year, 2, 9, 18, 45, tzinfo=datetime.timezone.utc),
            parse_datetime('Feb  9  18:45')[0]
        )

        self.assertEqual(
            datetime.datetime(
                2010, 5, 7, tzinfo=datetime.timezone.utc),
            parse_datetime('2010-05-07')[0]
        )

        self.assertEqual(
            datetime.datetime(
                2010, 5, 7, tzinfo=datetime.timezone.utc),
            parse_datetime('2010年5月7日')[0]
        )

        self.assertEqual(
            datetime.datetime(
                2010, 5, 7, tzinfo=datetime.timezone.utc),
            parse_datetime('07-05-2010')[0]
        )

        self.assertEqual(
            datetime.datetime(
                2010, 5, 7, tzinfo=datetime.timezone.utc),
            parse_datetime('07-05-2010')[0]
        )

        self.assertEqual(
            datetime.datetime(
                2014, 4, 1, 22, 39, tzinfo=datetime.timezone.utc),
            parse_datetime('Apr 1 2014 10:39PM', is_day_period=True)[0]
        )

        # TODO: more tests
