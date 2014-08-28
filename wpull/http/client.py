# encoding=utf-8
'''Basic HTTP Client.'''
import contextlib
import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.connection import ConnectionPool
from wpull.http.stream import Stream


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Client(object):
    '''Stateless HTTP/1.1 client.

    Args:
        connection_pool (:class:`.connection.ConnectionPool`): Connection pool.
        recorder (:class:`.recorder.BaseRecorder`): Recorder.
        stream_factory: A function that returns a new
            :class:`.http.stream.Stream`.
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
        '''Return a new session.

        Returns:
            Session.

        Context manager: This function is meant be used with the ``with``
        statement.
        '''
        if self._recorder:
            with self._recorder.session() as recorder_session:
                session = Session(self._connection_pool,
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
            session = Session(self._connection_pool,
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

        self._session_complete = True

    @trollius.coroutine
    def fetch(self, request):
        '''Fulfill a request.

        Args:
            request (:class:`.http.request.Request): Request.

        Returns:
            .http.request.Response

        Coroutine.
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
        request.address = connection.address

        self._connect_data_observer()

        if self._recorder_session:
            self._recorder_session.pre_request(request)

        yield From(stream.write_request(request))

        if request.body:
            assert 'Content-Length' in request.fields
            length = int(request.fields['Content-Length'])
            yield From(stream.write_body(request.body, length=length))

        if self._recorder_session:
            self._recorder_session.request(request)

        self._response = response = yield From(stream.read_response())
        response.request = request

        if self._recorder_session:
            self._recorder_session.pre_response(response)

        self._session_complete = False

        raise Return(response)

    @trollius.coroutine
    def read_content(self, file=None, raw=False, rewind=True):
        '''Read the response content into file.

        Args:
            file: A file object or asyncio stream.
            raw (bool): Whether chunked transfer encoding should be included.
            rewind: Seek the given file back to its original offset after
                reading is finished.

        Coroutine.
        '''
        if rewind and file and hasattr(file, 'seek'):
            original_offset = file.tell()
        else:
            original_offset = None

        if not hasattr(file, 'drain'):
            self._response.body = file

            if not isinstance(file, Body):
                self._response.body = Body(file)

        yield From(self._stream.read_body(self._request, self._response, file=file, raw=raw))
        self._session_complete = True

        if original_offset is not None:
            file.seek(original_offset)

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

    def done(self):
        '''Return whether the session was complete.

        A session is complete when it has sent a request,
        read the response header and the response body.
        '''
        return self._session_complete

    def close(self):
        '''Abort the session if not complete.'''
        if not self._session_complete and self._connection:
            self._connection.close()
            self._session_complete = True

    def clean(self):
        '''Return connection back to the pool.'''
        assert self._session_complete

        if self._connection:
            self._connection_pool.check_in(self._connection)
