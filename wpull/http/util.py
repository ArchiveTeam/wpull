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


def is_connection_close(http_version, connection_field):
    '''Return whether the Connection field is close.'''
    connection_field = (connection_field or '').lower()

    if http_version == 'HTTP/1.0':
        return connection_field.replace('-', '') != 'keepalive'
    else:
        return connection_field == 'close'
