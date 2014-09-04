'''Parse LIST listings.'''
import itertools

import wpull.ftp.ls.date
from wpull.ftp.ls.listing import LineParser


class ListingParser(object):
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

        self.listing_parser = LineParser()

    def run_heuristics(self):
        listing_type = self.listing_parser.guess_type(self.sample_lines)
        datetime_format = wpull.ftp.ls.date.guess_datetime_format(self.sample_lines)
        self.listing_parser.set_datetime_format(datetime_format)
        return listing_type, datetime_format

    def parse(self):
        return self.listing_parser.parse(self.lines)
