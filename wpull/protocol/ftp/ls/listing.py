'''Listing parser.'''
import re

import itertools
import namedlist

from wpull.protocol.ftp.ls.date import parse_datetime
import wpull.protocol.ftp.ls.date


FileEntry = namedlist.namedtuple(
    'FileEntryType',
    [
        'name',
        ('type', None),
        ('size', None),
        ('date', None),
        ('dest', None),
        ('perm', None)
    ])
'''A row in a listing.

Attributes:
    name (str): Filename.
    type (str, None): ``file``, ``dir``, ``symlink``, ``other``, ``None``
    size (int, None): Size of file.
    date (:class:`datetime.datetime`, None): A datetime object in UTC.
    dest (str, None): Destination filename for symlinks.
    perm (int, None): Unix permissions expressed as an integer.
'''


class ListingError(ValueError):
    '''Error during parsing a listing.'''


class UnknownListingError(ListingError):
    '''Failed to determine type of listing.'''


class LineParser(object):
    '''Parse individual lines in a listing.'''
    def __init__(self):
        self.type = None
        self.date_format = None
        self.is_day_period = None

    def guess_type(self, sample_lines):
        '''Guess the type of listing from a sample of lines.'''
        self.type = guess_listing_type(sample_lines)
        return self.type

    def set_datetime_format(self, datetime_format):
        '''Set the datetime format.'''
        self.date_format, self.is_day_period = datetime_format

    def parse(self, lines):
        '''Parse the lines.'''
        if self.type == 'msdos':
            return self.parse_msdos(lines)
        elif self.type == 'unix':
            return self.parse_unix(lines)
        elif self.type == 'nlst':
            return self.parse_nlst(lines)
        else:
            raise UnknownListingError('Unsupported listing type.')

    def parse_datetime(self, text):
        '''Parse datetime from line of text.'''
        return parse_datetime(text, date_format=self.date_format,
                              is_day_period=self.is_day_period)

    def parse_nlst(self, lines):
        '''Parse lines from a NLST format.'''
        for line in lines:
            yield FileEntry(line)

    def parse_msdos(self, lines):
        '''Parse lines from a MS-DOS format.'''
        for line in lines:
            fields = line.split(None, 4)

            date_str = fields[0]
            time_str = fields[1]

            datetime_str = '{} {}'.format(date_str, time_str)

            file_datetime = self.parse_datetime(datetime_str)[0]

            if fields[2] == '<DIR>':
                file_size = None
                file_type = 'dir'
            else:
                file_size = parse_int(fields[2])
                file_type = 'file'

            filename = fields[3]

            yield FileEntry(filename, file_type, file_size, file_datetime)

    def parse_unix(self, lines):
        '''Parse listings from a Unix ls command format.'''
        # This method uses some Filezilla parsing algorithms

        for line in lines:
            original_line = line
            fields = line.split(' ')
            after_perm_index = 0

            # Search for the permissions field by checking the file type
            for field in fields:
                after_perm_index += len(field)
                if not field:
                    continue

                # If the filesystem goes corrupt, it may show ? instead
                # but I don't really care in that situation.
                if field[0] in 'bcdlps-':
                    if field[0] == 'd':
                        file_type = 'dir'
                    elif field[0] == '-':
                        file_type = 'file'
                    elif field[0] == 'l':
                        file_type = 'symlink'
                    else:
                        file_type = 'other'

                    perms = parse_unix_perm(field[1:])

                    break
            else:
                raise ListingError('Failed to parse file type.')

            line = line[after_perm_index:]

            # We look for the position of the date and use the integer
            # before it as the file size.
            # We look for the position of the time and use the text
            # after it as the filename

            while line:
                try:
                    datetime_obj, start_index, end_index = self.parse_datetime(line)
                except ValueError:
                    line = line[4:]
                else:
                    break
            else:
                raise ListingError(
                    'Could parse a date from {}'.format(repr(original_line)))

            file_size = int(line[:start_index].rstrip().rpartition(' ')[-1])

            filename = line[end_index:].strip()

            if file_type == 'symlink':
                filename, sep, symlink_dest = filename.partition(' -> ')
            else:
                symlink_dest = None

            yield FileEntry(filename, file_type, file_size, datetime_obj,
                            symlink_dest, perm=perms)


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

        if '<DIR>' in line or re.search(r'^.{0,4}\d\d', line):
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
    '''Parse a integer containing potential grouping characters.'''
    text = text.translate(NUM_GROUPER_TABLE)
    return int(text)


def parse_unix_perm(text):
    '''Parse a Unix permission string and return integer value.'''
    # Based on ftp-ls.c symperms
    if len(text) != 9:
        return 0

    perms = 0

    for triad_index in range(3):
        string_index = triad_index * 3
        perms <<= 3

        if text[string_index] == 'r':
            perms |= 1 << 2

        if text[string_index + 1] == 'w':
            perms |= 1 << 1

        if text[string_index + 2] in 'xs':
            perms |= 1

    return perms


class ListingParser(LineParser):
    '''Listing parser.

    Args:
        text (str): A text listing.
        file: A file object in text mode containing the listing.
    '''
    def __init__(self, text=None, file=None):
        super().__init__()

        self._text = text
        self._file = file

    def parse_input(self):
        '''Parse the listings.

        Returns:
            iter: A iterable of :class:`.ftp.ls.listing.FileEntry`
        '''

        if self._text:
            lines = iter(self._text.splitlines())
        elif self._file:
            lines = self._file
        else:
            lines = ()

        sample_lines = []

        for line in lines:
            if len(sample_lines) > 100:
                break

            sample_lines.append(line)

        lines = itertools.chain(sample_lines, lines)

        self.guess_type(sample_lines)

        datetime_format = wpull.protocol.ftp.ls.date.guess_datetime_format(
            sample_lines)

        self.set_datetime_format(datetime_format)

        return self.parse(lines)
