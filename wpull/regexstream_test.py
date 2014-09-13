import io
import re
import unittest

from wpull.regexstream import RegexStream


class TestRegexStream(unittest.TestCase):
    def test_stream(self):
        my_file = io.StringIO('fish dog   horse bat dolphin')
        pattern = re.compile(r'(horse|dog|bat)')
        streamer = RegexStream(my_file, pattern, read_size=5, overlap_size=2)

        fragments = list(
            [(bool(match), text) for match, text in streamer.stream()])

        self.assertEqual(
            [
                (False, 'fish '),
                (True, 'dog'),
                (False, '  '),
                (False, ' '),
                (True, 'horse'),
                (False, ' '),
                (True, 'bat'),
                (False, ' dolp'),
                (False, 'hin'),
            ],
            fragments
        )
