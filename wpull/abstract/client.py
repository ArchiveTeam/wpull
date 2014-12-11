'''Client abstractions'''
import abc
import contextlib
import logging

from trollius import From, Return
import trollius

from wpull.connection import ConnectionPool


_logger = logging.getLogger(__name__)


class BaseClient(object, metaclass=abc.ABCMeta):
    '''Base client.'''
    def __init__(self, connection_pool=None, recorder=None,
                 proxy_adapter=None):
        '''
        Args:
            connection_pool (:class:`.connection.ConnectionPool`): Connection
                pool.
            recorder (:class:`.recorder.BaseRecorder`): Recorder.
            stream_factory: A function that returns a new
                :class:`.http.stream.Stream`.
            proxy_adapter (:class:`.http.proxy.ProxyAdapter`): Optional proxy.
        '''
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

        self._recorder = recorder
        self._proxy_adapter = proxy_adapter

    @abc.abstractmethod
    def _session_class(self):
        '''Return session class.'''

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
                session = self._session_class()(
                    connection_pool=self._connection_pool,
                    recorder_session=recorder_session,
                    proxy_adapter=self._proxy_adapter,
                )
                try:
                    yield session
                except Exception as error:
                    if not isinstance(error, StopIteration):
                        _logger.debug('Close session.')
                        session.close()
                    raise
                finally:
                    session.clean()
        else:
            session = self._session_class()(
                connection_pool=self._connection_pool,
                proxy_adapter=self._proxy_adapter,
                )
            try:
                yield session
            except Exception as error:
                if not isinstance(error, StopIteration):
                    _logger.debug('Close session.')
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
    def __init__(self, connection_pool=None, recorder_session=None,
                 proxy_adapter=None):
        assert connection_pool
        self._connection_pool = connection_pool
        self._recorder_session = recorder_session
        self._proxy_adapter = proxy_adapter

    @abc.abstractmethod
    def close(self):
        '''Close any connections.'''

    @abc.abstractmethod
    def clean(self):
        '''Return connection back to the pool.'''

    @trollius.coroutine
    def _check_out_connection(self, request):
        '''Return a connection.'''
        self._request = request
        host = request.url_info.hostname
        port = request.url_info.port
        ssl = request.url_info.scheme == 'https'

        if self._proxy_adapter:
            connection = yield From(
                self._proxy_adapter.check_out(self._connection_pool))

            yield From(self._proxy_adapter.connect(
                self._connection_pool, connection, (host, port), ssl))
        else:
            connection = yield From(
                self._connection_pool.check_out(host, port, ssl))

        self._connection = connection

        raise Return(connection)
