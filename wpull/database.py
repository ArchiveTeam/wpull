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
from sqlalchemy.sql.expression import select, insert, update, and_
from sqlalchemy.sql.schema import Column, ForeignKey
from sqlalchemy.sql.sqltypes import String, Integer, Boolean, Enum

from wpull.item import Status, URLRecord


_logger = logging.getLogger(__name__)
DBBase = declarative_base()


class DatabaseError(Exception):
    '''Any database error.'''
    pass


class NotFound(DatabaseError):
    '''Item not found in the table.'''
    pass


class URL(DBBase):
    __tablename__ = 'urls'
    id = Column(Integer, primary_key=True, autoincrement=True)
    url_str_id = Column(
        Integer, ForeignKey('url_strings.id'),
        nullable=False, unique=True, index=True
    )
    url_str_record = relationship(
        'URLString', uselist=False, foreign_keys=[url_str_id]
    )
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
        'URLString', uselist=False, foreign_keys=[top_url_str_id])
    top_url = association_proxy('top_url_record', 'url')
    status_code = Column(Integer)
    referrer_id = Column(Integer, ForeignKey('url_strings.id'))
    referrer_record = relationship(
        'URLString', uselist=False, foreign_keys=[referrer_id])
    referrer = association_proxy('referrer_record', 'url')
    inline = Column(Boolean)
    link_type = Column(String)
    url_encoding = Column(String)
    post_data = Column(String)
    filename = Column(String)

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
            self.filename,
        )


class URLString(DBBase):
    __tablename__ = 'url_strings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, nullable=False, unique=True, index=True)

    @classmethod
    def get_map(cls, session, urls):
        urls = tuple(urls)
        assert urls
        result_map = {}

        for batch in [urls[i:i + 500] for i in range(0, len(urls), 500)]:
            query = select([URLString])\
                .where(URLString.url.in_(batch))

            for row in session.execute(query):
                result_map[row.url] = row.id

        return result_map

    @classmethod
    def add_many(cls, session, urls):
        query = insert(URLString).prefix_with('OR IGNORE')
        session.execute(query, [{'url': url} for url in urls])


class Visit(DBBase):
    __tablename__ = 'visits'
    url = Column(String, primary_key=True, nullable=False)
    warc_id = Column(String, nullable=False)
    payload_digest = Column(String, nullable=False)


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
        pass


class BaseSQLURLTable(BaseURLTable):
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
            raise
        finally:
            session.close()

    def __getitem__(self, url):
        with self._session() as session:
            result = session.query(URL).filter_by(url=url).first()

            if not result:
                raise KeyError()
            else:
                return result.to_plain()

    def __iter__(self):
        with self._session() as session:
            return iter([record.url for record in session.query(URL)])

    def __len__(self):
        return self.count()

    def add(self, new_urls, **kwargs):
        assert not isinstance(new_urls, (str, bytes))
        referrer = kwargs.pop('referrer', None)
        top_url = kwargs.pop('top_url', None)
        url_strings = list(new_urls)

        if referrer:
            url_strings.append(referrer)

        if top_url:
            url_strings.append(top_url)

        with self._session() as session:
            URLString.add_many(session, url_strings)
            url_id_map = URLString.get_map(session, url_strings)

            for url in new_urls:
                values = dict(status=Status.todo)
                values.update(**kwargs)
                values['url_str_id'] = url_id_map[url]

                if referrer:
                    values['referrer_id'] = url_id_map[referrer]
                if top_url:
                    values['top_url_str_id'] = url_id_map[top_url]

                session.execute(
                    insert(URL).prefix_with('OR IGNORE'),
                    values
                )

    def get_and_update(self, status, new_status=None, level=None):
        with self._session() as session:
            if level is None:
                url_record = session.query(URL).filter_by(
                    status=status).first()
            else:
                url_record = session.query(URL)\
                    .filter(
                        URL.status == status,
                        URL.level < level,
                    ).first()

            if not url_record:
                raise NotFound()

            if new_status:
                url_record.status = new_status

            return url_record.to_plain()

    def update(self, url, increment_try_count=False, **kwargs):
        assert isinstance(url, str)

        with self._session() as session:
            values = {}
            url_id_map = URLString.get_map(session, [url])
            url_str_id = url_id_map[url]

            for key, value in kwargs.items():
                values[getattr(URL, key)] = value

            if increment_try_count:
                values[URL.try_count] = URL.try_count + 1

            query = update(URL)\
                .values(values)\
                .where(URL.url_str_id == url_str_id)

            session.execute(query)

    def count(self):
        with self._session() as session:
            return session.query(URL).count()

    def release(self):
        with self._session() as session:
            session.query(URL)\
                .filter_by(status=Status.in_progress)\
                .update({'status': Status.todo})

    def remove(self, urls):
        assert not isinstance(urls, (str, bytes))

        with self._session() as session:
            url_id_map = URLString.get_map(session, urls)

            for url in urls:
                if url not in url_id_map:
                    continue

                session.query(URL).filter_by(
                    url_str_id=url_id_map[url]).delete()

    def add_visits(self, visits):
        with self._session() as session:
            for url, warc_id, payload_digest in visits:
                session.execute(
                    insert(Visit).prefix_with('OR IGNORE'),
                    dict(
                        url=url,
                        warc_id=warc_id,
                        payload_digest=payload_digest
                    )
                )

    def get_revisit_id(self, url, payload_digest):
        query = select([Visit.warc_id]).where(
            and_(
                Visit.url == url,
                Visit.payload_digest == payload_digest
            )
        )

        with self._session() as session:
            row = session.execute(query).first()

            if row:
                return row.warc_id


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
    'URL', 'URLString',
    'BaseURLTable', 'SQLiteURLTable', 'GenericSQLURLTable',
    'URLTable',
]
