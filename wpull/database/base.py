'''Base table class.'''
import abc


class DatabaseError(Exception):
    '''Any database error.'''


class NotFound(DatabaseError):
    '''Item not found in the table.'''


class BaseURLTable(object, metaclass=abc.ABCMeta):
    '''URL table.'''

    @abc.abstractmethod
    def count(self):
        '''Return the number of URLs in the table.

        This call may be expensive.
        '''

    @abc.abstractmethod
    def get_one(self, url):
        '''Return a URLRecord for the URL.

        Returns:
            .item.URLRecord

        Raises:
            NotFound
        '''

    def contains(self, url):
        '''Return whether the URL is in the table.'''

        try:
            self.get_one(url)
        except NotFound:
            return False
        else:
            return True

    @abc.abstractmethod
    def get_all(self):
        '''Return all URLRecord.'''

    @abc.abstractmethod
    def add_many(self, urls, **kwargs):
        '''Add the URLs to the table.

        Args:
            urls: An iterable of `dict` column-value mapping. Each
                map must contain a ``url`` key.
            kwargs: Additional values to be saved for all the URLs

        Returns:
            list: The URLs added. Useful for tracking duplicates.
        '''

    def add_one(self, url, **kwargs):
        '''Add a single URL to the table.'''
        self.add_many([url], **kwargs)

    @abc.abstractmethod
    def check_out(self, filter_status, filter_level=None):
        '''Find a URL, mark it in progress, and return it.

        Args:
            filter_status: A status from :class:`.item.Status`.
            filter_level (int): Return an item with `level` or lower.

        Returns:
            .item.URLRecord

        Raises:
            NotFound
        '''

    @abc.abstractmethod
    def check_in(self, url, new_status, increment_try_count=True,
                 **kwargs):
        '''Update record for processed URL.

        Args:
            url (str): The URL.
            new_status: A status from :class:`.item.Status`.
            increment_try_count (bool): Whether to increment the try counter
                for the URL.
            kwargs: Additional values.
        '''

    @abc.abstractmethod
    def update_one(self, url, **kwargs):
        '''Arbitrarily update values for a URL.'''

    @abc.abstractmethod
    def release(self):
        '''Mark any ``in_progress`` URLs to ``todo`` status.'''

    @abc.abstractmethod
    def remove_many(self, urls):
        '''Remove the URLs from the database.'''

    def remove_one(self, url):
        '''Remove a URL from the database.'''
        self.remove_many([url])

    @abc.abstractmethod
    def close(self):
        '''Run any clean-up actions and close the table.'''

    @abc.abstractmethod
    def add_visits(self, visits):
        '''Add visited URLs from CDX file.

        Args:
            visits (iterable): An iterable of items. Each item is a tuple
                containing a URL, the WARC ID, and the payload digest.
        '''

    @abc.abstractmethod
    def get_revisit_id(self, url, payload_digest):
        '''Return the WARC ID corresponding to the visit.

        Returns:
            str, None
        '''
