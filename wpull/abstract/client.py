'''Client abstractions'''
import abc
import contextlib
import logging

from wpull.connection import ConnectionPool
from wpull.http.stream import Stream


_logger = logging.getLogger(__name__)


class BaseClient(object, metaclass=abc.ABCMeta):
    '''Base client.'''
    def __init__(self, connection_pool=None, recorder=None,
                 stream_factory=Stream):
        '''
        Args:
            connection_pool (:class:`.connection.ConnectionPool`): Connection
                pool.
            recorder (:class:`.recorder.BaseRecorder`): Recorder.
            stream_factory: A function that returns a new
                :class:`.http.stream.Stream`.
        '''
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

        self._recorder = recorder
        self._stream_factory = stream_factory

    @abc.abstractmethod
    def _session_class(self):
        pass

    @contextlib.contextmanager
    def session(self):
        '''Return a new session.

        Returns:
            BaseSession.

        Context manager: This function is meant be used with the ``with``
        statement.
        '''
        if self._recorder:
            with self._recorder.session() as recorder_session:
                session = self._session_class()(self._connection_pool,
                                                recorder_session,
                                                self._stream_factory)
                try:
                    yield session
                except Exception:
                    session.close()
                    raise
                finally:
                    session.clean()
        else:
            session = self._session_class()(self._connection_pool,
                                            None,
                                            self._stream_factory)
            try:
                yield session
            except Exception:
                session.close()
                raise
            finally:
                session.clean()

    def close(self):
        '''Close the connection pool and recorders.'''
        _logger.debug('Client closing.')
        self._connection_pool.close()

        if self._recorder:
            self._recorder.close()


class BaseSession(object, metaclass=abc.ABCMeta):
    '''Base session.'''
    def __init__(self, connection_pool, recorder_session, stream_factory):
        self._connection_pool = connection_pool
        self._recorder_session = recorder_session
        self._stream_factory = stream_factory

    @abc.abstractmethod
    def close(self):
        '''Close any connections.'''
        pass

    @abc.abstractmethod
    def clean(self):
        '''Return connection back to the pool.'''
        pass
