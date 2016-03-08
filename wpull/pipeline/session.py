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

    def add_child_urls(self, urls, inline=False, level=None, **kwargs):
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
            level=self._url_record.level + 1 if level is None else level,
            referrer=self._url_record.url,
            top_url=self._url_record.top_url or self._url_record.url,
            **kwargs
        )

    def child_url_record(self, url_info, inline=False,
                         link_type=None, post_data=None, level=None):
        '''Return a child URLRecord.

        This function is useful for testing filters before adding to table.
        '''
        return URLRecord(
            url_info.url,  # url
            Status.todo,  # status
            0,  # try_count
            self._url_record.level + 1 if level is None else level,  # level
            self._url_record.top_url or self._url_record.url,  # top_url
            None,  # status_code
            self._url_record.url,  # referrer
            (self._url_record.inline or 0) + 1 if inline else 0,  # inline
            link_type,  # link_type
            post_data,  # post_data
            None  # filename
        )


class ItemSession(object):
    pass
