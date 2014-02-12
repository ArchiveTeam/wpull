# encoding=utf-8
'''URL Tables.'''

import abc
import collections
import contextlib
import logging
from sqlalchemy.engine import create_engine
import sqlalchemy.event
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import String, Integer, Boolean, Enum

from wpull.cache import Cache
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
    ]
)


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
        }


class URLDBRecord(DBBase):
    __tablename__ = 'urls'
    id = Column(Integer, primary_key=True, autoincrement=True)
    url_str_id = Column(
        Integer, ForeignKey('url_strings.id'), nullable=False, index=True)
    url_str_record = relationship(
        'URLStrDBRecord', uselist=False, foreign_keys=[url_str_id])
    url = association_proxy('url_str_record', 'url')
    status = Column(
        Enum(
            Status.done, Status.error, Status.in_progress,
            Status.skipped, Status.todo,
        ),
        index=True,
        default=Status.todo,
        nullable=False,
    )
    try_count = Column(Integer, nullable=False, default=0)
    level = Column(Integer, nullable=False, default=0)
    top_url_str_id = Column(
        Integer, ForeignKey('url_strings.id'))
    top_url_record = relationship(
        'URLStrDBRecord', uselist=False, foreign_keys=[top_url_str_id])
    top_url = association_proxy('top_url_record', 'url')
    status_code = Column(Integer)
    referrer_id = Column(Integer, ForeignKey('url_strings.id'))
    referrer_record = relationship(
        'URLStrDBRecord', uselist=False, foreign_keys=[referrer_id])
    referrer = association_proxy('referrer_record', 'url')
    inline = Column(Boolean)
    link_type = Column(String)
    url_encoding = Column(String)
    post_data = Column(String)

    def to_plain(self):
        return URLRecord(
            self.url,
            self.status,
            self.try_count,
            self.level,
            self.top_url,
            self.status_code,
            self.referrer,
            self.inline,
            self.link_type,
            self.url_encoding,
            self.post_data,
        )


class URLStrDBRecord(DBBase):
    __tablename__ = 'url_strings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False, unique=True, index=True)

    @classmethod
    def get_url_id(cls, session, url, create=False, cache=None):
        if cache is not None:
            if url in cache:
                return cache[url]

        query = select([URLStrDBRecord.id])\
            .where(URLStrDBRecord.url == url).limit(1)
        row = session.execute(query).first()

        if row:
            record_id = row[0]
        else:
            record_id = None

        if create and not record_id:
            record = URLStrDBRecord(url=url)
            session.add(record)
            session.flush()
            record_id = record.id

        if record_id:
            if cache is not None:
                cache[url] = record_id
            return record_id


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

    @abc.abstractmethod
    def remove(self, urls):
        '''Remove the URLs from the database.'''
        pass

    @abc.abstractmethod
    def close(self):
        '''Run any clean-up actions and close the table.'''
        pass


class BaseSQLURLTable(BaseURLTable):
    def __init__(self):
        self._url_str_id_cache = Cache(max_items=100, time_to_live=600)
        self._url_item_added_cache = Cache(max_items=100, time_to_live=600)

    @abc.abstractproperty
    def _session_maker(self):
        pass

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
            self._url_str_id_cache.clear()
            self._url_item_added_cache.clear()
            raise
        finally:
            session.close()

    def __getitem__(self, url):
        with self._session() as session:
            result = session.query(URLDBRecord).filter_by(url=url).first()

            if not result:
                raise KeyError()
            else:
                return result.to_plain()

    def __iter__(self):
        with self._session() as session:
            return iter([record.url for record in session.query(URLDBRecord)])

    def __len__(self):
        return self.count()

    def add(self, urls, **kwargs):
        assert not isinstance(urls, (str, bytes))
        referrer = kwargs.pop('referrer', None)
        top_url = kwargs.pop('top_url', None)

        with self._session() as session:
            for url in urls:
                if url in self._url_item_added_cache:
                    continue

                url_str_id = URLStrDBRecord.get_url_id(
                    session, url, create=True, cache=self._url_str_id_cache)

                query = select([URLDBRecord.id])\
                    .where(URLDBRecord.url_str_id == url_str_id).limit(1)
                row = session.execute(query).first()

                if row:
                    continue

                values = dict(status=Status.todo)
                values.update(**kwargs)
                values['url_str_id'] = url_str_id

                if referrer:
                    values['referrer_id'] = URLStrDBRecord.get_url_id(
                        session, referrer, create=True,
                        cache=self._url_str_id_cache)
                if top_url:
                    values['top_url_str_id'] = URLStrDBRecord.get_url_id(
                        session, top_url, create=True,
                        cache=self._url_str_id_cache)

                session.execute(
                    URLDBRecord.__table__.insert(),
                    values
                )

                self._url_item_added_cache[url] = True

    def get_and_update(self, status, new_status=None, level=None):
        with self._session() as session:
            if level is None:
                url_record = session.query(URLDBRecord).filter_by(
                    status=status).first()
            else:
                url_record = session.query(URLDBRecord)\
                    .filter(
                        URLDBRecord.status == status,
                        URLDBRecord.level < level,
                    ).first()

            if not url_record:
                raise NotFound()

            if new_status:
                url_record.status = new_status

            return url_record.to_plain()

    def update(self, url, increment_try_count=False, **kwargs):
        assert isinstance(url, str)

        with self._session() as session:
            url_record = session.query(URLDBRecord).filter_by(url=url).first()

            if increment_try_count:
                url_record.try_count += 1

            for key, value in kwargs.items():
                setattr(url_record, key, value)

    def count(self):
        with self._session() as session:
            return session.query(URLDBRecord).count()

    def release(self):
        with self._session() as session:
            session.query(URLDBRecord)\
                .filter_by(status=Status.in_progress)\
                .update({'status': Status.todo})

    def remove(self, urls):
        assert not isinstance(urls, (str, bytes))

        with self._session() as session:
            for url in urls:
                url_str_id = URLStrDBRecord.get_url_id(
                    session, url, cache=self._url_str_id_cache)
                session.query(URLDBRecord).filter_by(
                    url_str_id=url_str_id).delete()

                if url in self._url_item_added_cache:
                    del self._url_item_added_cache[url]


class SQLiteURLTable(BaseSQLURLTable):
    '''URL table with SQLite storage.

    Args:
        path: A SQLite filename
    '''
    def __init__(self, path=':memory:'):
        super().__init__()
        # We use a SingletonThreadPool always because we are using WAL
        # and want SQLite to handle the checkpoints. Otherwise NullPool
        # will open and close the connection rapidly, defeating the purpose
        # of WAL.
        self._engine = create_engine(
            'sqlite:///{0}'.format(path), poolclass=SingletonThreadPool)
        sqlalchemy.event.listen(
            self._engine, 'connect', self._apply_pragmas_callback)
        DBBase.metadata.create_all(self._engine)
        self._session_maker_instance = sessionmaker(bind=self._engine)

    @classmethod
    def _apply_pragmas_callback(cls, connection, record):
        '''Set SQLite pragmas.

        Write-ahead logging is used.
        '''
        _logger.debug('Setting pragmas.')
        connection.execute('PRAGMA journal_mode=WAL')

    @property
    def _session_maker(self):
        return self._session_maker_instance

    def close(self):
        self._engine.dispose()


class GenericSQLURLTable(BaseSQLURLTable):
    '''URL table using SQLAlchemy without any customizations.

    Args:
        url: A SQLAlchemy database URL.
    '''
    def __init__(self, url):
        super().__init__()
        self._engine = create_engine(url)
        DBBase.metadata.create_all(self._engine)
        self._session_maker_instance = sessionmaker(bind=self._engine)

    @property
    def _session_maker(self):
        return self._session_maker_instance

    def close(self):
        self._engine.dispose()


URLTable = SQLiteURLTable
'''The default URL table implementation.'''


__all__ = [
    'DatabaseError', 'NotFound', 'Status',
    'URLRecord', 'URLDBRecord', 'URLStrDBRecord',
    'BaseURLTable', 'SQLiteURLTable', 'GenericSQLURLTable',
    'URLTable',
]
