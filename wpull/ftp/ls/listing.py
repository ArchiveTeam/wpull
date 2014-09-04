'''Listing parser.'''
import collections
import re

from wpull.ftp.ls.date import parse_datetime


FileEntry = collections.namedtuple(
    'FileEntryType', ['name', 'type', 'size', 'date'])
'''A row in a listing.

Attributes:
    name (str): Filename.
    type (str): ``file``, ``dir``, ``other``, ``None``
    size (int): Size of file.
    date (:class:`datetime.datetime`): A datetime object in UTC.
'''


class LineParser(object):
    def __init__(self):
        self.type = None
        self.date_format = None
        self.hour_period = None

    def guess_type(self, sample_lines):
        self.type = guess_listing_type(sample_lines)
        return self.type

    def set_datetime_format(self, datetime_format):
        self.date_format, self.hour_period = datetime_format

    def parse(self, lines):
        if self.type == 'msdos':
            return self.parse_msdos(lines)

    def parse_datetime(self, text):
        return parse_datetime(text, date_format=self.date_format,
                              hour_period=self.hour_period)

    def parse_nlst(self, lines):
        entries = []
        for line in lines:
            entries.append(FileEntry(line, None, None, None))
        return entries

    def parse_msdos(self, lines):
        entries = []
        for line in lines:
            fields = line.split(None, 4)

            date_str = fields[0]
            time_str = fields[1]

            datetime_str = '{} {}'.format(date_str, time_str)

            file_datetime = self.parse_datetime(datetime_str)

            if fields[2] == '<DIR>':
                file_size = None
                file_type = 'dir'
            else:
                file_size = parse_int(fields[2])
                file_type = 'file'

            filename = fields[3]

            entries.append(
                FileEntry(filename, file_type, file_size, file_datetime))

        return entries

    def parse_unix(self, lines):
        # TODO: write me
        pass


def guess_listing_type(lines, threshold=100):
    '''Guess the style of directory listing.

    Returns:
        str: ``unix``, ``msdos``, ``nlst``, ``unknown``.
    '''
    scores = {
        'unix': 0,
        'msdos': 0,
        'nlst': 0,
    }
    for line in lines:
        if not line:
            continue

        if re.search(r'---|r--|rw-|rwx', line):
            scores['unix'] += 1

        if '<DIR>' in line:
            scores['msdos'] += 1

        words = line.split(' ', 1)

        if len(words) == 1:
            scores['nlst'] += 1

        if max(scores.values()) > threshold:
            break

    top = max(scores.items(), key=lambda item: item[1])

    if top[1]:
        return top[0]
    else:
        return 'unknown'


NUM_GROUPER_TABLE = str.maketrans('', '', ' ,')


def parse_int(text):
    text = text.translate(NUM_GROUPER_TABLE)
    return int(text)
