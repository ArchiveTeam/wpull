'''Parse LIST listings.'''
import collections
import itertools
import unicodedata

import wpull.ftp.ls.date
import wpull.ftp.ls.heuristic


FileEntry = collections.namedtuple(
    'FileEntryType', ['name', 'type', 'size', 'date'])
'''A row in a listing.

Attributes:
    name (str): Filename.
    type (str): ``file``, ``dir``, ``other``, ``None``
    size (int): Size of file.
    date (:class:`datetime.datetime`): A datetime object in UTC.
'''


def parse(text=None, file=None):
    '''Parse a directory listing.

    Attributes:
        text (str): The directory listing.
        file: A file containing the directory listing.

    Returns:
        list: A list of `FileEntry`.
    '''
    if text:
        sample_text = text
        lines = text.splitlines()
    elif file:
        sample_lines = []
        for line in file:
            if len(sample_lines) > 100:
                break
            sample_lines.append(line)
        sample_text = '\n'.join(sample_lines)
        lines = itertools.chain(sample_lines, file)

    listing_type = wpull.ftp.ls.heuristic.guess_listing_type(sample_text)

    if listing_type == 'unix':
        return parse_unix(lines)
    elif listing_type == 'msdos':
        return parse_msdos(lines)
    else:
        return parse_nlst(lines)


def parse_nlst(lines):
    entries = []
    for line in lines:
        entries.append(FileEntry(line, None, None, None))
    return entries


def parse_msdos(lines):
    entries = []
    for line in lines:
        fields = line.split(None, 4)

        date_str = fields[0]
        time_str = fields[1]

        datetime_str = '{} {}'.format(date_str, time_str)

        file_datetime = wpull.ftp.ls.date.parse_datetime(datetime_str)

        if fields[2] == '<DIR>':
            file_size = None
            file_type = 'dir'
        else:
            file_size = parse_int(fields[2])
            file_type = 'file'

        filename = fields[3]

        entries.append(
            FileEntry(file_datetime, file_type, file_size, filename))

    return entries


def parse_unix(lines):
    pass


NUM_GROUPER_TABLE = str.maketrans('', '', ' ,')


def parse_int(text):
    text = unicodedata.normalize('NFKD', text)
    text = text.translate(NUM_GROUPER_TABLE)
    return int(text)
