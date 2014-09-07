'''Misc functions.'''


import gettext
import logging
import mimetypes
import re

from wpull.backport.logging import BraceMessage as __
import wpull.url


_ = gettext.gettext
_logger = logging.getLogger(__name__)


def parse_refresh(text):
    '''Parses text for HTTP Refresh URL.

    Returns:
        str, None
    '''
    match = re.search(r'url\s*=(.+)', text, re.IGNORECASE)

    if match:
        url = match.group(1)

        if url.startswith('"'):
            url = url.strip('"')
        elif url.startswith("'"):
            url = url.strip("'")

        return clean_link_soup(url)


def clean_link_soup(link):
    '''Strip whitespace from a link in HTML soup.

    Args:
        link (str): A string containing the link with lots of whitespace.

    The link is split into lines. For each line, leading and trailing
    whitespace is removed and tabs are removed throughout. The lines are
    concatenated and returned.

    For example, passing the ``href`` value of::

        <a href=" http://example.com/

                blog/entry/

            how smaug stole all the bitcoins.html
        ">

    will return
    ``http://example.com/blog/entry/how smaug stole all the bitcoins.html``.

    Returns:
        str: The cleaned link.
    '''
    return ''.join(
        [line.strip().replace('\t', '') for line in link.splitlines()]
    )


def urljoin_safe(base_url, url, allow_fragments=True):
    '''urljoin with warning log on error.

    Returns:
        str, None'''
    try:
        return wpull.url.urljoin(
            base_url, url, allow_fragments=allow_fragments
        )
    except ValueError as error:
        _logger.warning(__(
            _('Discarding malformed URL ‘{url}’: {error}.'),
            url=url, error=error
        ))


def is_likely_inline(link):
    '''Return whether the link is likely to be inline.'''
    file_type = mimetypes.guess_type(link, strict=False)[0]

    if file_type:
        prefix_type = file_type.split('/', 1)[0]

        return prefix_type in ('image', 'video', 'audio')
