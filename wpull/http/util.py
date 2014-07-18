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


def should_close(http_version, connection_field):
    '''Return whether the connection should be closed.

    Args:
        http_version (str): The HTTP version string like ``HTTP/1.0``.
        connection_field (str): The value for the ``Connection`` header.
    '''
    connection_field = (connection_field or '').lower()

    if http_version == 'HTTP/1.0':
        return connection_field.replace('-', '') != 'keepalive'
    else:
        return connection_field == 'close'
