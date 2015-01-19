# encoding=utf-8
'''URL items.'''
import collections
import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.url import URLInfo


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Status(object):
    '''URL status.'''
    todo = 'todo'
    '''The item has not yet been processed.'''
    in_progress = 'in_progress'
    '''The item is in progress of being processed.'''
    done = 'done'
    '''The item has been processed successfully.'''
    error = 'error'
    '''The item encountered an error during processing.'''
    skipped = 'skipped'
    '''The item was excluded from processing due to some rejection filters.'''


_URLRecordType = collections.namedtuple(
    'URLRecordType',
    [
        'url',
        'status',
        'try_count',
        'level',
        'top_url',
        'status_code',
        'referrer',
        'inline',
        'link_type',
        'post_data',
        'filename',
    ]
)


class LinkType(object):
    '''The type of contents that a link is expected to have.'''
    html = 'html'
    '''HTML document.'''
    css = 'css'
    '''Stylesheet file. Recursion on links is usually safe.'''
    javascript = 'javascript'
    '''JavaScript file. Possible to recurse links on this file.'''
    media = 'media'
    '''Image or video file. Recursion on this type will not be useful.'''
    sitemap = 'sitemap'
    '''A Sitemap.xml file.'''


class URLRecord(_URLRecordType):
    '''An entry in the URL table describing a URL to be downloaded.

    Attributes:
        url (str): The URL.
        status (str): The status as specified from :class:`Status`.
        try_count (int): The number of attempts on this URL.
        level (int): The recursive depth of this URL. A level of ``0``
            indicates the URL was initially supplied to the program (the
            top URL).
            Level ``1`` means the URL was linked from the top URL.
        top_url (str): The earliest ancestor URL of this URL. The `top_url`
            is typically the URL supplied at the start of the program.
        status_code (int): The HTTP status code.
        referrer (str): The parent URL that linked to this URL.
        inline (int): Whether this URL was an embedded object (such as an
            image or a stylesheet) of the parent URL.

            The value represents the recursive depth of the object. For
            example, an iframe is depth 1 and the images in the iframe
            is depth 2.

        link_type (str): Describes the document type. Values are:

            * ``html``: HTML document
            * ``css``: CSS document

        post_data (str): If given, the URL should be fetched as a
            POST request containing `post_data`.
        filename (str): The path to where the file was saved.
    '''
    @property
    def url_info(self):
        '''Return an :class:`.url.URLInfo` for the ``url``.'''
        return URLInfo.parse(self.url)

    @property
    def referrer_info(self):
        '''Return an :class:`.url.URLInfo` for the ``referrer``.'''
        return URLInfo.parse(self.referrer)

    def to_dict(self):
        '''Return the values as a ``dict``.

        In addition to the attributes, it also includes the ``url_info`` and
        ``referrer_info`` properties converted to ``dict`` as well.
        '''
        return {
            'url': self.url,
            'status': self.status,
            'url_info': self.url_info.to_dict(),
            'try_count': self.try_count,
            'level': self.level,
            'top_url': self.top_url,
            'status_code': self.status_code,
            'referrer': self.referrer,
            'referrer_info':
                self.referrer_info.to_dict() if self.referrer else None,
            'inline': self.inline,
            'link_type': self.link_type,
            'post_data': self.post_data,
            'filename': self.filename,
        }


class URLItem(object):
    '''Item for a URL that needs to processed.'''
    def __init__(self, url_table, url_info, url_record):
        self._url_table = url_table
        self._url_info = url_info
        self._url_record = url_record
        self._url = self._url_record.url
        self._processed = False
        self._try_count_incremented = False

    @property
    def url_info(self):
        '''Return the :class:`.url.URLInfo`.'''
        return self._url_info

    @property
    def url_record(self):
        '''Return the :class:`URLRecord`.'''
        return self._url_record

    @property
    def url_table(self):
        '''Return the :class:`.database.URLTable`.'''
        return self._url_table

    @property
    def is_processed(self):
        '''Return whether the item has been processed.'''
        return self._processed

    def skip(self):
        '''Mark the item as processed without download.'''
        _logger.debug(__(_('Skipping ‘{url}’.'), url=self._url))
        self._url_table.check_in(self._url, Status.skipped)

        self._processed = True

    def set_status(self, status, increment_try_count=True, filename=None):
        '''Mark the item with the given status.

        Args:
            status (int): a value from :class:`Status`.
            increment_try_count (bool): if True, increment the ``try_count``
                value
        '''
        assert not self._try_count_incremented, (self._url, status)

        if increment_try_count:
            self._try_count_incremented = True

        _logger.debug(__('Marking URL {0} status {1}.', self._url, status))
        self._url_table.check_in(
            self._url,
            status,
            increment_try_count=increment_try_count,
            filename=filename,
        )

        self._processed = True

    def set_value(self, **kwargs):
        '''Set values for the URL in table.'''
        self._url_table.update_one(self._url, **kwargs)

    def add_child_url(self, url, inline=False, **kwargs):
        '''Add a single URL as a child of this item.

        See :meth:`add_child_urls` for argument details.
        '''
        self.add_child_urls([{'url': url}], inline=inline, **kwargs)

    def add_child_urls(self, urls, inline=False, **kwargs):
        '''Add links scraped from the document with automatic values.

        Args:
            urls: An iterable of `str` or `dict`. When a `str` is provided,
                it is a URL. When a `dict` is provided, it is a mapping
                of table column names to values.
            inline (bool): Whether the URL is an embedded object. This
                function automatically calculates the value needed for
                the table column "inline".
            kwargs: Additional column value to be apllied for all URLs
                provided.

        This function provides values automatically for:

        * ``inline``
        * ``level``
        * ``referrer``
        * ``top_url``

        See also :meth:`.database.base.BaseSQLURLTable.add_many`.
        '''
        self._url_table.add_many(
            [item if isinstance(item, dict) else {'url': item} for item in urls],
            inline=(self._url_record.inline or 0) + 1 if inline else None,
            level=self._url_record.level + 1,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            **kwargs
        )

    def child_url_record(self, url_info, inline=False,
                         link_type=None, post_data=None):
        '''Return a child URLRecord.

        This function is useful for testing filters before adding to table.
        '''
        return URLRecord(
            url_info.url,  # url
            Status.todo,  # status
            0,  # try_count
            self._url_record.level + 1,  # level
            self._url_record.top_url or self._url_record.url,  # top_url
            None,  # status_code
            self._url_record.url,  # referrer
            (self._url_record.inline or 0) + 1 if inline else 0,  # inline
            link_type,  # link_type
            post_data,  # post_data
            None  # filename
        )
