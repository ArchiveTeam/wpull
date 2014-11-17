'''Misc functions.'''

import logging

from wpull.backport.logging import BraceMessage as __
import wpull.http.util
import wpull.util
import wpull.string


_logger = logging.getLogger(__name__)


def get_heading_encoding(response):
    '''Return the document encoding from a HTTP header.

    Args:
        response (Response): An instance of :class:`.http.Response`.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.util.parse_charset(
        response.fields.get('content-type', ''))

    if encoding:
        return wpull.string.normalize_codec_name(encoding)
    else:
        return None


def detect_response_encoding(response, is_html=False, peek=131072):
    '''Return the likely encoding of the response document.

    Args:
        response (Response): An instance of :class:`.http.Response`.
        is_html (bool): See :func:`.util.detect_encoding`.
        peek (int): The maximum number of bytes of the document to be analyzed.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = get_heading_encoding(response)

    encoding = wpull.string.detect_encoding(
        wpull.util.peek_file(response.body, peek), encoding=encoding, is_html=is_html
    )

    _logger.debug(__('Got encoding: {0}', encoding))

    return encoding


def is_gzip(data):
    '''Return whether the data is likely to be gzip.'''
    return data.startswith(b'\x1f\x8b')
