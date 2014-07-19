# encoding=utf-8
'''Basic HTTP Client.'''
import contextlib
import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.connection import ConnectionPool
from wpull.http.stream import Stream


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Client(object):
    '''Stateless HTTP/1.1 client.

    Args:
        connection_pool (:class:`.connection.ConnectionPool`): Connection pool.
        recorder (:class:`.recorder.BaseRecorder`): Recorder.
        stream_factory: A function that returns a new :class:`.stream.Stream`.
    '''
    def __init__(self, connection_pool=None, recorder=None,
                 stream_factory=Stream):
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

        self._recorder = recorder
        self._stream_factory = stream_factory

    @contextlib.contextmanager
    def session(self):
        '''Return a new session context manager.

        Returns:
            Session.
        '''
        if self._recorder:
            with self._recorder.session() as recorder_session:
                session = Session(self._connection_pool,
                                  recorder_session,
                                  self._stream_factory)
        else:
            session = Session(self._connection_pool,
                              None,
                              self._stream_factory)

        try:
            yield session
        finally:
            session.clean_up()

    def close(self):
        '''Close the connection pool and recorders.'''
        _logger.debug('Client closing.')
        self._connection_pool.close()

        if self._recorder:
            self._recorder.close()


class Session(object):
    '''HTTP request and response session.'''
    def __init__(self, connection_pool, recorder_session, stream_factory):
        self._connection_pool = connection_pool
        self._recorder_session = recorder_session
        self._stream_factory = stream_factory

        self._connection = None
        self._stream = None
        self._request = None
        self._response = None

    @trollius.coroutine
    def fetch(self, request):
        '''Fulfill a request.

        Args:
            request (:class:`.http.request.Request): Request.

        Returns:
            .http.request.Response
        '''
        _logger.debug(__('Client fetch request {0}.', request))

        self._request = request

        request.prepare_for_send()

        host = request.url_info.hostname
        port = request.url_info.port
        ssl = request.url_info.scheme == 'https'

        self._connection = connection = yield From(self._connection_pool
                                                   .check_out(host, port, ssl))
        self._stream = stream = self._stream_factory(connection)

        self._connect_data_observer()

        if self._recorder_session:
            self._recorder_session.pre_request(request)

        yield From(stream.write_request(request))

        if request.body:
            yield From(stream.write_body(request.body))

        if self._recorder_session:
            self._recorder_session.request(request)

        self._response = response = yield From(stream.read_response())
        response.request = request

        if self._recorder_session:
            self._recorder_session.pre_response(response)

        raise Return(response)

    @trollius.coroutine
    def read_content(self, file=None):
        '''Read the response content into file.'''
        yield From(self._stream.read_body(self._request, self._response, file))

        if self._recorder_session:
            self._recorder_session.response(self._response)

    def _connect_data_observer(self):
        '''Connect the stream data observer to the recorder.'''
        if self._recorder_session:
            self._stream.data_observer.add(self._data_callback)

    def _data_callback(self, data_type, data):
        '''Stream data observer callback.'''
        if data_type in ('request', 'request_body'):
            self._recorder_session.request_data(data)
        elif data_type in ('response', 'response_body'):
            self._recorder_session.response_data(data)

    def clean_up(self):
        '''Return connection back to the pool.'''
        if self._connection:
            self._connection_pool.check_in(self._connection)
