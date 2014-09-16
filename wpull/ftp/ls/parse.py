'''Parse LIST listings.'''
import itertools

import wpull.ftp.ls.date
from wpull.ftp.ls.listing import LineParser


class ListingParser(object):
    '''Listing parser.

    Args:
        text (str): A text listing.
        file: A file object in text mode containing the listing.
    '''
    def __init__(self, text=None, file=None):
        if text:
            self.lines = text.splitlines()
            self.sample_lines = self.lines[:100]
        elif file:
            sample_lines = []
            for line in file:
                if len(sample_lines) > 100:
                    break
                sample_lines.append(line)
            self.lines = itertools.chain(sample_lines, file)
            self.sample_lines = sample_lines

        self.line_parser = LineParser()

    def run_heuristics(self):
        '''Run heuristics on a sample of lines.

        Returns:
            tuple: Information about the result. The tuple contains
            the listing type and the datetime format.
        '''
        listing_type = self.line_parser.guess_type(self.sample_lines)
        datetime_format = wpull.ftp.ls.date.guess_datetime_format(self.sample_lines)
        self.line_parser.set_datetime_format(datetime_format)
        return listing_type, datetime_format

    def parse(self):
        '''Parse the listings.

        Call :meth:`run_heuristics` first.

        Returns:
            list: A list of :class:`.ftp.ls.listing.FileEntry`
        '''
        return self.line_parser.parse(self.lines)
