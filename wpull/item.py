# encoding=utf-8
'''URL items.'''
import collections
import gettext
import logging

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
        'url_encoding',
        'post_data',
        'filename',
    ]
)


class LinkType(object):
    '''The type of contents that a link is expected to have.'''
    html = 'html'
    '''html document.'''
    css = 'css'
    '''stylesheet.'''


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
        inline (bool): Whether this URL was an embedded object (such as an
            image or a stylesheet) of the parent URL.
        link_type (str): Describes the document type. Values are:

            * ``html``: HTML document
            * ``css``: CSS document

        url_encoding (str): The name of the codec used to encode/decode
            the URL. See :class:`.url.URLInfo`.
        post_data (str): If given, the URL should be fetched as a
            POST request containing `post_data`.
        filename (str): The path to where the file was saved.
    '''
    @property
    def url_info(self):
        '''Return an :class:`.url.URLInfo` for the ``url``.'''
        return URLInfo.parse(self.url, encoding=self.url_encoding or 'utf8')

    @property
    def referrer_info(self):
        '''Return an :class:`.url.URLInfo` for the ``referrer``.'''
        return URLInfo.parse(
            self.referrer, encoding=self.url_encoding or 'utf8')

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
            'url_encoding': self.url_encoding,
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
        _logger.debug(_('Skipping ‘{url}’.').format(url=self._url))
        self._url_table.update(self._url, status=Status.skipped)

        self._processed = True

    def set_status(self, status, increment_try_count=True, filename=None):
        '''Mark the item with the given status.

        Args:
            status (int): a value from :class:`Status`.
            increment_try_count (bool): if True, increment the ``try_count``
                value
        '''
        assert not self._try_count_incremented

        if increment_try_count:
            self._try_count_incremented = True

        _logger.debug('Marking URL {0} status {1}.'.format(self._url, status))
        self._url_table.update(
            self._url,
            increment_try_count=increment_try_count,
            status=status,
            filename=filename,
        )

        self._processed = True

    def set_value(self, **kwargs):
        '''Set values for the URL in table.'''
        self._url_table.update(self._url, **kwargs)

    def add_inline_url_infos(self, url_infos, encoding=None, link_type=None,
    post_data=None):
        '''Add inline links scraped from the document.

        Args:
            url_infos (iterable): A list of :class:`.url.URLInfo`
            encoding (str): The encoding of the document.
        '''
        inline_urls = tuple([info.url for info in url_infos])
        _logger.debug('Adding inline URLs {0}'.format(inline_urls))
        self._url_table.add(
            inline_urls,
            inline=True,
            level=self._url_record.level + 1,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            url_encoding=encoding,
            post_data=post_data,
        )

    def add_linked_url_infos(self, url_infos, encoding=None, link_type=None,
    post_data=None):
        '''Add linked links scraped from the document.

        Args:
            url_infos (iterable): A list of :class:`.url.URLInfo`
            encoding (str): The encoding of the document.
        '''
        linked_urls = tuple([info.url for info in url_infos])
        _logger.debug('Adding linked URLs {0}'.format(linked_urls))
        self._url_table.add(
            linked_urls,
            level=self._url_record.level + 1,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            link_type=link_type,
            url_encoding=encoding,
            post_data=post_data,
        )

    def child_url_record(self, url_info, inline=False, encoding=None,
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
            inline,  # inline
            link_type,  # link_type
            encoding,  # url_encoding
            post_data,  # post_data
            None  # filename
        )
