# encoding=utf-8
'''URL Tables.'''

import abc
import collections
import contextlib
import logging
from sqlalchemy.engine import create_engine
import sqlalchemy.event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.session import sessionmaker, make_transient
import sqlalchemy.sql.expression
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import String, Integer, Boolean, Enum

from wpull.url import URLInfo


_logger = logging.getLogger(__name__)
DBBase = declarative_base()


class DatabaseError(Exception):
    '''Any database error.'''
    pass


class NotFound(DatabaseError):
    '''Item not found in the table.'''
    pass


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


class URLRecord(DBBase):
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
        link_type (str): Describes the document type. The only value used
            is ``html`` for HTML documents.
        url_encoding (str): The name of the codec used to encode/decode
            the URL. See :class:`.url.URLInfo`.
        post_data (str): If given, the URL should be fetched as a
            POST request containing `post_data`.
    '''
    __tablename__ = 'urls'
    url = Column(String, primary_key=True)
    status = Column(
        Enum(
            Status.done, Status.error, Status.in_progress,
            Status.skipped, Status.todo,
        ),
        index=True,
    )
    try_count = Column(Integer, nullable=False, default=0)
    level = Column(Integer, nullable=False, default=0)
    top_url = Column(String)
    status_code = Column(Integer)
    referrer = Column(String)
    inline = Column(Boolean)
    link_type = Column(String)
    url_encoding = Column(String)
    post_data = Column(String)

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
        }


class BaseURLTable(collections.Mapping, object, metaclass=abc.ABCMeta):
    '''URL table.'''
    def __init__(self):
        super().__init__()

    @abc.abstractmethod
    def add(self, urls, **kwargs):
        '''Add the URLs to the table.

        Args:
            urls: An iterable of URL strings
            kwargs: Additional values to be saved for all the URLs
        '''
        pass

    @abc.abstractmethod
    def get_and_update(self, status, new_status=None, level=None):
        '''Find a URL, mark it in progress, and return it.'''
        pass

    @abc.abstractmethod
    def update(self, url, increment_try_count=False, **kwargs):
        '''Set values for the URL.'''
        pass

    @abc.abstractmethod
    def count(self):
        '''Return the number of URLs in the table.'''
        pass

    @abc.abstractmethod
    def release(self):
        '''Mark any ``in_progress`` URLs to ``todo`` status.'''
        pass


class SQLiteURLTable(BaseURLTable):
    '''URL table with SQLite storage.

    Args:
        path: A SQLite filename
    '''
    def __init__(self, path=':memory:'):
        super().__init__()
        self._engine = create_engine('sqlite:///{0}'.format(path))
        sqlalchemy.event.listen(
            self._engine, 'connect', self._apply_pragmas_callback)
        DBBase.metadata.create_all(self._engine)
        self._session_maker = sessionmaker(bind=self._engine)

    @classmethod
    def _apply_pragmas_callback(cls, connection, record):
        '''Set SQLite pragmas.

        Write-ahead logging is used.
        '''
        _logger.debug('Setting pragmas.')
        connection.execute('PRAGMA journal_mode=WAL')

    @contextlib.contextmanager
    def _session(self):
        """Provide a transactional scope around a series of operations."""
        # Taken from the session docs.
        session = self._session_maker()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def __getitem__(self, url):
        with self._session() as session:
            result = session.query(URLRecord).get(url)

            if not result:
                raise IndexError()
            else:
                make_transient(result)
                return result

    def __iter__(self):
        with self._session() as session:
            return session.query(URLRecord.url)

    def __len__(self):
        return self.count()

    def add(self, urls, **kwargs):
        assert not isinstance(urls, (str, bytes))

        with self._session() as session:
            inserter = sqlalchemy.sql.expression.insert(URLRecord)\
                .prefix_with('OR IGNORE')

            for url in urls:
                session.execute(
                    inserter,
                    dict(url=url, status=Status.todo, **kwargs)
                )

    def get_and_update(self, status, new_status=None, level=None):
        with self._session() as session:
            if level is None:
                url_record = session.query(URLRecord).filter_by(
                    status=status).first()
            else:
                url_record = session.query(URLRecord)\
                    .filter(
                        URLRecord.status == status,
                        URLRecord.level < level,
                    ).first()

            if not url_record:
                raise NotFound()

            if new_status:
                url_record.status = new_status

            make_transient(url_record)
            return url_record

    def update(self, url, increment_try_count=False, **kwargs):
        assert isinstance(url, str)

        with self._session() as session:
            url_record = session.query(URLRecord).get(url)

            if increment_try_count:
                url_record.try_count += 1

            for key, value in kwargs.items():
                setattr(url_record, key, value)

    def count(self):
        with self._session() as session:
            return session.query(URLRecord).count()

    def release(self):
        with self._session() as session:
            session.query(URLRecord)\
                .filter_by(status=Status.in_progress)\
                .update({'status': Status.todo})


URLTable = SQLiteURLTable
'''The default URL table implementation.'''
