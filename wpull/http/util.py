# encoding=utf-8
'''Miscellaneous HTTP functions.'''
import re


def parse_charset(header_string):
    '''Parse a "Content-Type" string for the document encoding.

    Returns:
        str, None
    '''
    match = re.search(
        r'''charset[ ]?=[ ]?["']?([a-z0-9_-]+)''',
        header_string,
        re.IGNORECASE
    )

    if match:
        return match.group(1)
