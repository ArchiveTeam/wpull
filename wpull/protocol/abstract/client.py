'''Client abstractions'''
import abc
import asyncio
import contextlib
import enum
import logging

from typing import Optional, Callable, TypeVar, Generic

from wpull.application.hook import HookableMixin
from wpull.errors import NetworkTimedOut
from wpull.network.pool import ConnectionPool

_logger = logging.getLogger(__name__)


@contextlib.contextmanager
def dummy_context_manager():
    yield None


class DurationTimeout(NetworkTimedOut):
    '''Download did not complete within specified time.'''


class BaseSession(HookableMixin, metaclass=abc.ABCMeta):
    '''Base session.'''

    class SessionEvent(enum.Enum):
        begin_session = 'begin_session'
        end_session = 'end_session'

    def __init__(self, connection_pool):
        super().__init__()
        self._connection_pool = connection_pool
        self._connections = set()

        self.event_dispatcher.register(self.SessionEvent.begin_session)
        self.event_dispatcher.register(self.SessionEvent.end_session)

    def __enter__(self):
        self.event_dispatcher.notify(self.SessionEvent.begin_session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val and not isinstance(exc_val, StopIteration):
            _logger.debug('Early close session.')
            error = True
            self.abort()
        else:
            error = False

        self.recycle()
        self.event_dispatcher.notify(self.SessionEvent.end_session, error=error)

    def abort(self):
        '''Terminate early and close any connections.'''
        for connection in self._connections:
            connection.close()

    def recycle(self):
        '''Clean up and return connections back to the pool.

        Connections should be kept alive if supported.
        '''

        for connection in self._connections:
            self._connection_pool.no_wait_release(connection)

        self._connections.clear()

    @asyncio.coroutine
    def _acquire_request_connection(self, request):
        '''Return a connection.'''
        host = request.url_info.hostname
        port = request.url_info.port
        use_ssl = request.url_info.scheme == 'https'
        tunnel = request.url_info.scheme != 'http'

        connection = yield from self._acquire_connection(host, port, use_ssl, tunnel)

        return connection

    @asyncio.coroutine
    def _acquire_connection(self, host, port, use_ssl=False, tunnel=True):
        '''Return a connection.'''
        if hasattr(self._connection_pool, 'acquire_proxy'):
            connection = yield from \
                self._connection_pool.acquire_proxy(host, port, use_ssl,
                                                    tunnel=tunnel)
        else:
            connection = yield from \
                self._connection_pool.acquire(host, port, use_ssl)

        self._connections.add(connection)

        return connection


SessionT = TypeVar('SessionT')


class BaseClient(Generic[SessionT], HookableMixin, metaclass=abc.ABCMeta):
    '''Base client.'''

    class ClientEvent(enum.Enum):
        new_session = 'new_session'

    def __init__(self, connection_pool: Optional[ConnectionPool]=None):
        '''
        Args:
            connection_pool: Connection pool.
        '''
        super().__init__()
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

        self.event_dispatcher.register(self.ClientEvent.new_session)

    @abc.abstractmethod
    def _session_class(self) -> Callable[[], SessionT]:
        '''Return session class.'''
        return BaseSession  # return something for code checkers

    def session(self) -> SessionT:
        '''Return a new session.'''
        session = self._session_class()(
            connection_pool=self._connection_pool,
        )
        self.event_dispatcher.notify(self.ClientEvent.new_session, session)
        return session

    def close(self):
        '''Close the connection pool.'''
        _logger.debug('Client closing.')
        self._connection_pool.close()


