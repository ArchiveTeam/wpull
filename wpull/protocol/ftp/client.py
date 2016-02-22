'''FTP client.'''
import enum
import io
import logging
import weakref
import functools


import asyncio

from typing import IO, Tuple
from typing import Optional

from wpull.protocol.abstract.client import BaseClient, BaseSession, DurationTimeout
from wpull.body import Body
from wpull.errors import ProtocolError, AuthenticationError
from wpull.protocol.ftp.command import Commander
from wpull.protocol.ftp.ls.listing import ListingError, ListingParser
from wpull.protocol.ftp.request import Response, Command, ListingResponse, \
    Request
from wpull.protocol.ftp.stream import ControlStream
from wpull.protocol.ftp.util import FTPServerError, ReplyCodes
import wpull.protocol.ftp.util


_logger = logging.getLogger(__name__)


class SessionState(enum.Enum):
    ready = 'ready'
    file_request_sent = 'file_request_sent'
    directory_request_sent = 'directory_request_sent'
    response_received = 'response_received'
    aborted = 'aborted'


class Session(BaseSession):
    def __init__(self, login_table: weakref.WeakKeyDictionary, **kwargs):
        self._login_table = login_table

        super().__init__(**kwargs)

        self._control_connection = None
        self._control_stream = None
        self._commander = None
        self._request = None
        self._response = None
        self._data_stream = None
        self._data_connection = None
        self._listing_type = None
        self._session_state = SessionState.ready

    @asyncio.coroutine
    def _init_stream(self):
        '''Create streams and commander.

        Coroutine.
        '''
        assert not self._control_connection
        self._control_connection = yield from self._acquire_request_connection(self._request)
        self._control_stream = ControlStream(self._control_connection)
        self._commander = Commander(self._control_stream)

        # if self._recorder_session:
        #     def control_data_callback(direction, data):
        #         assert direction in ('command', 'reply'), \
        #             'Expect read/write. Got {}'.format(repr(direction))
        #
        #         if direction == 'reply':
        #             self._recorder_session.response_control_data(data)
        #         else:
        #             self._recorder_session.request_control_data(data)
        #
        #     self._control_stream.data_observer.add(control_data_callback)

    @asyncio.coroutine
    def _log_in(self):
        '''Connect and login.

        Coroutine.
        '''
        username = self._request.url_info.username or self._request.username or 'anonymous'
        password = self._request.url_info.password or self._request.password or '-wpull@'

        cached_login = self._login_table.get(self._control_connection)

        if cached_login and cached_login == (username, password):
            _logger.debug('Reusing existing login.')
            return

        try:
            yield from self._commander.login(username, password)
        except FTPServerError as error:
            raise AuthenticationError('Login error: {}'.format(error)) \
                from error

        self._login_table[self._control_connection] = (username, password)

    @asyncio.coroutine
    def start(self, request: Request) -> Response:
        '''Start a file or directory listing download.

        Args:
            request: Request.

        Returns:
            A Response populated with the initial data connection reply.

        Once the response is received, call :meth:`download`.

        Coroutine.
        '''
        if self._session_state != SessionState.ready:
            raise RuntimeError('Session not ready')

        response = Response()

        yield from self._prepare_fetch(request, response)

        response.file_transfer_size = yield from self._fetch_size(request)

        if request.restart_value:
            try:
                yield from self._commander.restart(request.restart_value)
                response.restart_value = request.restart_value
            except FTPServerError:
                _logger.debug('Could not restart file.', exc_info=1)

        yield from self._open_data_stream()

        command = Command('RETR', request.file_path)

        yield from self._begin_stream(command)

        self._session_state = SessionState.file_request_sent

        return response

    @asyncio.coroutine
    def start_listing(self, request: Request) -> ListingResponse:
        '''Fetch a file listing.

        Args:
            request: Request.

        Returns:
            A listing response populated with the initial data connection
            reply.

        Once the response is received, call :meth:`download_listing`.

        Coroutine.
        '''
        if self._session_state != SessionState.ready:
            raise RuntimeError('Session not ready')

        response = ListingResponse()

        yield from self._prepare_fetch(request, response)
        yield from self._open_data_stream()

        mlsd_command = Command('MLSD', self._request.file_path)
        list_command = Command('LIST', self._request.file_path)

        try:
            yield from self._begin_stream(mlsd_command)
            self._listing_type = 'mlsd'
        except FTPServerError as error:
            if error.reply_code in (ReplyCodes.syntax_error_command_unrecognized,
                                    ReplyCodes.command_not_implemented):
                self._listing_type = None
            else:
                raise

        if not self._listing_type:
            # This code not in exception handler to avoid incorrect
            # exception chaining
            yield from self._begin_stream(list_command)
            self._listing_type = 'list'

        _logger.debug('Listing type is %s', self._listing_type)

        self._session_state = SessionState.directory_request_sent

        return response

    @asyncio.coroutine
    def _prepare_fetch(self, request: Request, response: Response):
        '''Prepare for a fetch.

        Coroutine.
        '''
        self._request = request
        self._response = response

        yield from self._init_stream()

        connection_closed = self._control_connection.closed()

        if connection_closed:
            self._login_table.pop(self._control_connection, None)
            yield from self._control_stream.reconnect()

        request.address = self._control_connection.address

        # if self._recorder_session:
        #     connection_reused = not connection_closed
        #     self._recorder_session.begin_control(
        #         request, connection_reused=connection_reused
        #     )

        if connection_closed:
            yield from self._commander.read_welcome_message()

        yield from self._log_in()

        self._response.request = request

    @asyncio.coroutine
    def _begin_stream(self, command: Command):
        '''Start data stream transfer.'''
        begin_reply = yield from self._commander.begin_stream(command)

        self._response.reply = begin_reply

        # if self._recorder_session:
        #     self._recorder_session.pre_response(self._response)

    @asyncio.coroutine
    def download(self, file: Optional[IO]=None, rewind: bool=True,
                 duration_timeout: Optional[float]=None) -> Response:
        '''Read the response content into file.

        Args:
            file: A file object or asyncio stream.
            rewind: Seek the given file back to its original offset after
                reading is finished.
            duration_timeout: Maximum time in seconds of which the
                entire file must be read.

        Returns:
            A Response populated with the final data connection reply.

        Be sure to call :meth:`start` first.

        Coroutine.
        '''
        if self._session_state != SessionState.file_request_sent:
            raise RuntimeError('File request not sent')

        if rewind and file and hasattr(file, 'seek'):
            original_offset = file.tell()
        else:
            original_offset = None

        if not hasattr(file, 'drain'):
            self._response.body = file

            if not isinstance(file, Body):
                self._response.body = Body(file)

        read_future = self._commander.read_stream(file, self._data_stream)

        try:
            reply = yield from \
                asyncio.wait_for(read_future, timeout=duration_timeout)
        except asyncio.TimeoutError as error:
            raise DurationTimeout(
                'Did not finish reading after {} seconds.'
                .format(duration_timeout)
            ) from error

        self._response.reply = reply

        if original_offset is not None:
            file.seek(original_offset)

        # if self._recorder_session:
        #     self._recorder_session.response(self._response)

        self._session_state = SessionState.response_received

        return self._response

    @asyncio.coroutine
    def download_listing(self, file: Optional[IO],
                         duration_timeout: Optional[float]=None) -> \
            ListingResponse:
        '''Read file listings.

        Args:
            file: A file object or asyncio stream.
            duration_timeout: Maximum time in seconds of which the
                entire file must be read.

        Returns:
            A Response populated the file listings

        Be sure to call :meth:`start_file_listing` first.

        Coroutine.
        '''
        if self._session_state != SessionState.directory_request_sent:
            raise RuntimeError('File request not sent')

        self._session_state = SessionState.file_request_sent

        yield from self.download(file=file, rewind=False,
                                 duration_timeout=duration_timeout)

        try:
            if self._response.body.tell() == 0:
                listings = ()
            elif self._listing_type == 'mlsd':
                self._response.body.seek(0)

                machine_listings = wpull.protocol.ftp.util.parse_machine_listing(
                    self._response.body.read().decode('utf-8',
                                                      errors='surrogateescape'),
                    convert=True, strict=False
                )
                listings = list(
                    wpull.protocol.ftp.util.machine_listings_to_file_entries(
                        machine_listings
                    ))
            else:
                self._response.body.seek(0)

                file = io.TextIOWrapper(self._response.body, encoding='utf-8',
                                        errors='surrogateescape')

                listing_parser = ListingParser(file=file)

                listings = list(listing_parser.parse_input())

                _logger.debug('Listing detected as %s', listing_parser.type)

                # We don't want the file to be closed when exiting this function
                file.detach()

        except (ListingError, ValueError) as error:
            raise ProtocolError(*error.args) from error

        self._response.files = listings

        self._response.body.seek(0)

        self._session_state = SessionState.response_received

        return self._response

    @asyncio.coroutine
    def _open_data_stream(self):
        '''Open the data stream connection.

        Coroutine.
        '''
        @asyncio.coroutine
        def connection_factory(address: Tuple[int, int]):
            self._data_connection = yield from self._acquire_connection(address[0], address[1])
            return self._data_connection

        self._data_stream = yield from self._commander.setup_data_stream(
            connection_factory
        )

        # if self._recorder_session:
        #     self._response.data_address = self._data_connection.address
        #
        #     def data_callback(action, data):
        #         if action == 'read':
        #             self._recorder_session.response_data(data)
        #
        #     self._data_stream.data_observer.add(data_callback)

    @asyncio.coroutine
    def _fetch_size(self, request: Request) -> int:
        '''Return size of file.

        Coroutine.
        '''
        try:
            size = yield from self._commander.size(request.file_path)
            return size
        except FTPServerError:
            return

    def abort(self):
        super().abort()
        self._close_data_connection()

        if self._control_connection:
            self._login_table.pop(self._control_connection, None)

    def recycle(self):
        super().recycle()
        self._close_data_connection()

        # if self._control_connection:
        #     if self._recorder_session:
        #         self._recorder_session.end_control(
        #             self._response, connection_closed=self._control_connection.closed()
        #         )

    def _close_data_connection(self):
        if self._data_connection:
            # self._data_connection.close()
            # self._connection_pool.no_wait_release(self._data_connection)
            self._data_connection = None

        if self._data_stream:
            self._data_stream.data_observer.clear()
            self._data_stream = None


class Client(BaseClient[Session]):
    '''FTP Client.

    The session object is :class:`Session`.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._login_table = weakref.WeakKeyDictionary()

    def _session_class(self) -> Session:
        return functools.partial(Session, login_table=self._login_table)
