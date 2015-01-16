'''FTP client.'''
import io
import logging

from trollius import From, Return
import trollius

from wpull.abstract.client import BaseClient, BaseSession
from wpull.body import Body
from wpull.errors import ProtocolError
from wpull.ftp.command import Commander
from wpull.ftp.ls.listing import ListingError
from wpull.ftp.ls.parse import ListingParser
from wpull.ftp.request import Response, Command, ListingResponse
from wpull.ftp.stream import ControlStream
from wpull.ftp.util import FTPServerError, ReplyCodes
import wpull.ftp.util


_logger = logging.getLogger(__name__)


class Client(BaseClient):
    '''FTP Client.

    The session object is :class:`Session`.
    '''
    def _session_class(self):
        return Session


class Session(BaseSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._connection = None
        self._control_stream = None
        self._commander = None
        self._request = None
        self._response = None
        self._data_stream = None
        self._data_connection = None
        self._listing_type = None

        # TODO: maybe keep track of sessions among connections to avoid
        # having to login over and over again

    @trollius.coroutine
    def _init_stream(self):
        '''Create streams and commander.

        Coroutine.
        '''
        assert not self._connection
        self._connection = yield From(
            self._connection_pool.check_out(
                self._request.url_info.hostname, self._request.url_info.port
            ))
        self._control_stream = ControlStream(self._connection)
        self._commander = Commander(self._control_stream)

        if self._recorder_session:
            def control_data_callback(direction, data):
                assert direction in ('command', 'reply'), \
                    'Expect read/write. Got {}'.format(repr(direction))

                if direction == 'reply':
                    self._recorder_session.response_control_data(data)
                else:
                    self._recorder_session.request_control_data(data)

            self._control_stream.data_observer.add(control_data_callback)

    @trollius.coroutine
    def _log_in(self):
        '''Connect and login.

        Coroutine.
        '''
        username = self._request.url_info.username or self._request.username or 'anonymous'
        password = self._request.url_info.password or self._request.password or '-wpull@'

        yield From(self._commander.reconnect())
        yield From(self._commander.login(username, password))

    @trollius.coroutine
    def fetch(self, request):
        '''Fulfill a request.

        Args:
            request (:class:`.ftp.request.Request`): Request.

        Returns:
            .ftp.request.Response: A Response populated with the initial
            data connection reply.

        Once the response is received, call :meth:`read_content`.

        Coroutine.
        '''
        response = Response()

        yield From(self._prepare_fetch(request, response))

        response.file_transfer_size = yield From(self._fetch_size(request))

        if request.restart_value:
            try:
                yield From(self._commander.restart(request.restart_value))
                response.restart_value = request.restart_value
            except FTPServerError:
                _logger.debug('Could not restart file.', exc_info=1)

        yield From(self._open_data_stream())

        command = Command('RETR', request.url_info.path)

        yield From(self._begin_stream(command))

        raise Return(response)

    @trollius.coroutine
    def fetch_file_listing(self, request):
        '''Fetch a file listing.

        Returns:
            .ftp.request.ListingResponse

        Once the response is received, call :meth:`read_listing_content`.

        Coroutine.
        '''
        response = ListingResponse()

        yield From(self._prepare_fetch(request, response))
        yield From(self._open_data_stream())

        mlsd_command = Command('MLSD', self._request.url_info.path)
        list_command = Command('LIST', self._request.url_info.path)

        try:
            yield From(self._begin_stream(mlsd_command))
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
            yield From(self._begin_stream(list_command))
            self._listing_type = 'list'

        _logger.debug('Listing type is %s', self._listing_type)

        raise Return(response)

    @trollius.coroutine
    def _prepare_fetch(self, request, response):
        '''Prepare for a fetch.

        Coroutine.
        '''
        self._request = request
        self._response = response

        yield From(self._init_stream())

        request.address = self._connection.address

        if self._recorder_session:
            self._recorder_session.begin_control(request)

        yield From(self._log_in())

        self._response.request = request

    @trollius.coroutine
    def _begin_stream(self, command):
        '''Start data stream transfer.'''
        begin_reply = yield From(self._commander.begin_stream(command))

        self._response.reply = begin_reply

        if self._recorder_session:
            self._recorder_session.pre_response(self._response)

    @trollius.coroutine
    def read_content(self, file=None, rewind=True):
        '''Read the response content into file.

        Args:
            file: A file object or asyncio stream.
            rewind: Seek the given file back to its original offset after
                reading is finished.

        Returns:
            .ftp.request.Response: A Response populated with the final
            data connection reply.

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

        reply = yield From(self._commander.read_stream(
            file, self._data_stream
        ))

        self._response.reply = reply

        if original_offset is not None:
            file.seek(original_offset)

        if self._recorder_session:
            self._recorder_session.response(self._response)

        raise Return(self._response)

    @trollius.coroutine
    def read_listing_content(self, file):
        '''Read file listings.

        Returns:
            .ftp.request.ListingResponse: A Response populated the
            file listings

        Be sure to call :meth:`fetch_file_listing` first.

        Coroutine.
        '''
        yield From(self.read_content(file=file, rewind=False))

        try:
            if self._response.body.tell() == 0:
                listings = ()
            elif self._listing_type == 'mlsd':
                self._response.body.seek(0)

                listings = wpull.ftp.util.parse_machine_listing(
                    self._response.body.read().decode('latin-1'),
                    convert=True, strict=False
                )
            else:
                self._response.body.seek(0)

                file = io.TextIOWrapper(self._response.body, encoding='latin-1')

                listing_parser = ListingParser(file=file)
                heuristics_result = listing_parser.run_heuristics()

                _logger.debug('Listing detected as %s', heuristics_result)

                listings = listing_parser.parse()

                # We don't want the file to be closed when exiting this function
                file.detach()

        except (ListingError, ValueError) as error:
            raise ProtocolError(*error.args) from error

        self._response.files = listings

        self._response.body.seek(0)
        raise Return(self._response)

    @trollius.coroutine
    def _open_data_stream(self):
        '''Open the data stream connection.

        Coroutine.
        '''
        @trollius.coroutine
        def connection_factory(address):
            self._data_connection = yield From(
                self._connection_pool.check_out(address[0], address[1]))
            raise Return(self._data_connection)

        self._data_stream = yield From(self._commander.setup_data_stream(
            connection_factory
        ))

        if self._recorder_session:
            self._response.data_address = self._data_connection.address

            def data_callback(action, data):
                if action == 'read':
                    self._recorder_session.response_data(data)

            self._data_stream.data_observer.add(data_callback)

    @trollius.coroutine
    def _fetch_size(self, request):
        '''Return size of file.

        Coroutine.
        '''
        try:
            size = yield From(self._commander.size(request.url_info.path))
            raise Return(size)
        except FTPServerError:
            return

    def clean(self):
        if self._connection:
            if self._recorder_session:
                self._recorder_session.end_control(self._response)

            self._connection_pool.check_in(self._connection)

        if self._data_connection:
            self._data_connection.close()
            self._connection_pool.check_in(self._data_connection)

        if self._data_stream:
            self._data_stream.data_observer.clear()

    def close(self):
        if self._connection:
            self._connection.close()
