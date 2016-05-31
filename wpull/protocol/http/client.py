# encoding=utf-8
'''Basic HTTP Client.'''
import enum
import functools
import gettext
import logging
import warnings

import asyncio

from typing import Optional, Union, IO, Callable

from wpull.application.hook import HookableMixin
from wpull.protocol.abstract.client import BaseClient, BaseSession, DurationTimeout
from wpull.backport.logging import BraceMessage as __
from wpull.body import Body
from wpull.protocol.http.request import Request, Response
from wpull.protocol.http.stream import Stream


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class SessionState(enum.Enum):
    ready = 'ready'
    request_sent = 'request_sent'
    response_received = 'response_received'
    aborted = 'aborted'


class Session(BaseSession):
    '''HTTP request and response session.'''

    class Event(enum.Enum):
        begin_request = 'begin_request'
        request_data = 'request_data'
        end_request = 'end_request'
        begin_response = 'begin_response'
        response_data = 'response_data'
        end_response = 'end_response'

    def __init__(self, stream_factory: Callable[..., Stream]=None, **kwargs):
        super().__init__(**kwargs)

        assert stream_factory
        self._stream_factory = stream_factory
        self._stream = None
        self._request = None
        self._response = None

        self._session_state = SessionState.ready

        self.event_dispatcher.register(self.Event.begin_request)
        self.event_dispatcher.register(self.Event.request_data)
        self.event_dispatcher.register(self.Event.end_request)
        self.event_dispatcher.register(self.Event.begin_response)
        self.event_dispatcher.register(self.Event.response_data)
        self.event_dispatcher.register(self.Event.end_response)

    @asyncio.coroutine
    def start(self, request: Request) -> Response:
        '''Begin a HTTP request

        Args:
            request: Request information.

        Returns:
            A response populated with the HTTP headers.

        Once the headers are received, call :meth:`download`.

        Coroutine.
        '''
        if self._session_state != SessionState.ready:
            raise RuntimeError('Session already started')

        assert not self._request
        self._request = request
        _logger.debug(__('Client fetch request {0}.', request))

        connection = yield from self._acquire_request_connection(request)
        full_url = connection.proxied and not connection.tunneled

        self._stream = stream = self._stream_factory(connection)

        yield from self._stream.reconnect()

        request.address = connection.address

        self.event_dispatcher.notify(self.Event.begin_request, request)
        write_callback = functools.partial(self.event_dispatcher.notify, self.Event.request_data)
        stream.data_event_dispatcher.add_write_listener(write_callback)

        yield from stream.write_request(request, full_url=full_url)

        if request.body:
            assert 'Content-Length' in request.fields
            length = int(request.fields['Content-Length'])
            yield from stream.write_body(request.body, length=length)

        stream.data_event_dispatcher.remove_write_listener(write_callback)
        self.event_dispatcher.notify(self.Event.end_request, request)

        read_callback = functools.partial(self.event_dispatcher.notify, self.Event.response_data)
        stream.data_event_dispatcher.add_read_listener(read_callback)

        self._response = response = yield from stream.read_response()
        response.request = request

        self.event_dispatcher.notify(self.Event.begin_response, response)

        self._session_state = SessionState.request_sent

        return response

    @asyncio.coroutine
    def download(
            self,
            file: Union[IO[bytes], asyncio.StreamWriter, None]=None,
            raw: bool=False, rewind: bool=True,
            duration_timeout: Optional[float]=None):
        '''Read the response content into file.

        Args:
            file: A file object or asyncio stream.
            raw: Whether chunked transfer encoding should be included.
            rewind: Seek the given file back to its original offset after
                reading is finished.
            duration_timeout: Maximum time in seconds of which the
                entire file must be read.

        Be sure to call :meth:`start` first.

        Coroutine.
        '''
        if self._session_state != SessionState.request_sent:
            raise RuntimeError('Request not sent')

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
            yield from asyncio.wait_for(read_future, timeout=duration_timeout)
        except asyncio.TimeoutError as error:
            raise DurationTimeout(
                'Did not finish reading after {} seconds.'
                    .format(duration_timeout)
            ) from error

        self._session_state = SessionState.response_received

        if original_offset is not None:
            file.seek(original_offset)

        self.event_dispatcher.notify(self.Event.end_response, self._response)
        self.recycle()

    def done(self) -> bool:
        '''Return whether the session was complete.

        A session is complete when it has sent a request,
        read the response header and the response body.
        '''
        return self._session_state == SessionState.response_received

    def abort(self):
        super().abort()

        self._session_state = SessionState.aborted

    def recycle(self):
        if not self.done():
            super().abort()
            warnings.warn(_('HTTP session did not complete.'))

        super().recycle()


class Client(BaseClient):
    '''Stateless HTTP/1.1 client.

    The session object is :class:`Session`.
    '''
    def __init__(self, *args, stream_factory=Stream, **kwargs):
        super().__init__(*args, **kwargs)
        self._stream_factory = stream_factory

    def _session_class(self) -> Callable[[], Session]:
        return functools.partial(Session, stream_factory=self._stream_factory)

    def session(self) -> Session:
        return super().session()
