'''Client abstractions'''
import abc
import contextlib
import logging

from trollius import From, Return
import trollius

from wpull.connection import ConnectionPool
from wpull.errors import NetworkTimedOut


_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def dummy_context_manager():
    yield None


class DurationTimeout(NetworkTimedOut):
    '''Download did not complete within specified time.'''


class BaseClient(object, metaclass=abc.ABCMeta):
    '''Base client.'''
    def __init__(self, connection_pool=None, recorder=None):
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

    @abc.abstractmethod
    def _session_class(self):
        '''Return session class.'''
        return BaseSession  # return something for code checkers

    @contextlib.contextmanager
    def session(self):
        '''Return a new session.

        Returns:
            BaseSession.

        Context manager: This function is meant be used with the ``with``
        statement.
        '''
        if self._recorder:
            context_manager = self._recorder.session()
        else:
            context_manager = dummy_context_manager()

        with context_manager as recorder_session:
            session = self._session_class()(
                connection_pool=self._connection_pool,
                recorder_session=recorder_session,
            )
            try:
                yield session
            except Exception as error:
                if not isinstance(error, StopIteration):
                    _logger.debug('Early close session.')
                    session.abort()
                    session.recycle()
                raise
            else:
                session.recycle()

    def close(self):
        '''Close the connection pool and recorders.'''
        _logger.debug('Client closing.')
        self._connection_pool.close()

        if self._recorder:
            self._recorder.close()


class BaseSession(object, metaclass=abc.ABCMeta):
    '''Base session.'''
    def __init__(self, connection_pool=None, recorder_session=None):
        assert connection_pool
        self._connection_pool = connection_pool
        self._recorder_session = recorder_session
        self._request = None
        self._connection = None

    @abc.abstractmethod
    def abort(self):
        '''Terminate early and close any connections.'''

    @abc.abstractmethod
    def recycle(self):
        '''Clean up and return connection back to the pool.

        Connections should be kept alive if supported.
        '''

    @trollius.coroutine
    def _acquire_connection(self, request):
        '''Return a connection.'''
        self._request = request
        host = request.url_info.hostname
        port = request.url_info.port
        use_ssl = request.url_info.scheme == 'https'
        tunnel = request.url_info.scheme != 'http'

        if hasattr(self._connection_pool, 'acquire_proxy'):
            connection = yield From(
                self._connection_pool.acquire_proxy(host, port, use_ssl,
                                                    tunnel=tunnel))
        else:
            connection = yield From(
                self._connection_pool.acquire(host, port, use_ssl))

        self._connection = connection

        raise Return(connection)
