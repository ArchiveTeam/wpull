'''Utils'''
import re


def parse_address(text):
    '''Parse PASV address.'''
    match = re.search(
        r'\('
        r'(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*,'
        r'\s*(\d{1,3})\s*'
        r'\)',
        text)

    if match:
        return (
            '{0}.{1}.{2}.{3}'.format(int(match.group(1)),
                                     int(match.group(2)),
                                     int(match.group(3)),
                                     int(match.group(4))
                                     ),
            int(match.group(5)) << 8 | int(match.group(6))
            )
    else:
        raise ValueError('No address found')


def reply_code_tuple(code):
    '''Return the reply code as a tuple.

    Args:
        code (int): The reply code.

    Returns:
        tuple: Each item is the digit.
    '''
    return (code // 100, code // 10 % 10, code % 10)
