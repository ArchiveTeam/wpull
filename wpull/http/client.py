# encoding=utf-8
'''Basic HTTP Client.'''
import gettext
import logging
import tornado.gen
import toro

from wpull.conversation import BaseClient
from wpull.http.connection import ConnectionPool
from wpull.recorder import DemuxRecorder


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Client(BaseClient):
    '''HTTP/1.1 client.

    Args:
        connection_pool (ConnectionPool): An instance of
            :class:`ConnectionPool`.
        recorder (Recorder): An instance of :class:`.recorder.BaseRecorder`.

    This HTTP client manages connection pooling to reuse existing
    connections if possible.
    '''
    def __init__(self, connection_pool=None, recorder=None):
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

        self._recorder = recorder

    @tornado.gen.coroutine
    def fetch(self, request, **kwargs):
        '''Fetch a document.

        Args:
            request (Request): An instance of :class:`Request`.
            kwargs: Any keyword arguments to pass to :func:`Connection.fetch`.

        Returns:
            Response: An instance of :class:`Response`.

        Raises:
            Exception: See :meth:`.http.connection.Connection.fetch`.
        '''
        _logger.debug('Client fetch request {0}.'.format(request))

        if 'recorder' not in kwargs:
            kwargs['recorder'] = self._recorder
        elif self._recorder:
            kwargs['recorder'] = DemuxRecorder(
                (kwargs['recorder'], self._recorder)
            )

        async_result = toro.AsyncResult()
        yield self._connection_pool.put(request, kwargs, async_result)
        response = yield async_result.get()
        if isinstance(response, Exception):
            raise response from response
        else:
            raise tornado.gen.Return(response)

    def close(self):
        '''Close the connection pool and recorders.'''
        _logger.debug('Client closing.')
        self._connection_pool.close()

        if self._recorder:
            self._recorder.close()
