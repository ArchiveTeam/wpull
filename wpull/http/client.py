# encoding=utf-8
'''Basic HTTP Client.'''
import functools
import gettext
import logging
import warnings

from trollius import From, Return
import trollius

from wpull.abstract.client import BaseClient, BaseSession, DurationTimeout
from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.http.stream import Stream


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Client(BaseClient):
    '''Stateless HTTP/1.1 client.

    The session object is :class:`Session`.
    '''
    def __init__(self, stream_factory=Stream, **kwargs):
        super().__init__(**kwargs)
        self._stream_factory = stream_factory

    def _session_class(self):
        return functools.partial(Session, stream_factory=self._stream_factory)


class Session(BaseSession):
    '''HTTP request and response session.'''
    def __init__(self, stream_factory=None, **kwargs):
        super().__init__(**kwargs)

        assert stream_factory
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
            request (:class:`.http.request.Request`): Request.

        Returns:
            .http.request.Response: A Response populated with the HTTP headers.

        Once the headers are received, call :meth:`read_content`.

        Coroutine.
        '''
        assert not self._connection
        _logger.debug(__('Client fetch request {0}.', request))

        connection = yield From(self._acquire_connection(request))
        full_url = connection.proxied and not connection.tunneled

        self._stream = stream = self._stream_factory(connection)
        request.address = connection.address

        self._connect_data_observer()

        if self._recorder_session:
            self._recorder_session.pre_request(request)

        yield From(stream.write_request(request, full_url=full_url))

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
    def read_content(self, file=None, raw=False, rewind=True,
                     duration_timeout=None):
        '''Read the response content into file.

        Args:
            file: A file object or asyncio stream.
            raw (bool): Whether chunked transfer encoding should be included.
            rewind (bool): Seek the given file back to its original offset after
                reading is finished.
            duration_timeout (int): Maximum time in seconds of which the
                entire file must be read.

        Be sure to call :meth:`fetch` first.

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

        read_future = self._stream.read_body(self._request, self._response, file=file, raw=raw)

        try:
            yield From(trollius.wait_for(read_future, timeout=duration_timeout))
        except trollius.TimeoutError as error:
            raise DurationTimeout(
                'Did not finish reading after {} seconds.'
                .format(duration_timeout)
            ) from error

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

    def abort(self):
        if self._connection:
            self._connection.close()

        self._session_complete = True

    def recycle(self):
        if not self._session_complete:
            warnings.warn(_('HTTP session did not complete.'))

            self.abort()

        if self._connection:
            self._connection_pool.no_wait_release(self._connection)
