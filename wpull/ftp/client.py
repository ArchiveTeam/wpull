'''FTP client.'''
import io

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
        # TODO: grab defaults from options
        username = self._request.url_info.username or 'anonymous'
        password = self._request.url_info.password or '-wpull@'

        yield From(self._commander.reconnect())
        yield From(self._commander.login(username, password))

    @trollius.coroutine
    def fetch(self, request, file=None, callback=None):
        '''Fetch a file.

        Returns:
            .ftp.request.Response

        Coroutine.
        '''
        response = Response()

        yield From(self._prepare_fetch(request, response, file, callback))

        reply = yield From(self._fetch_with_command(
            Command('RETR', request.url_info.path), response.body
        ))

        self._clean_up_fetch(reply)

        raise Return(response)

    @trollius.coroutine
    def fetch_file_listing(self, request, file=None, callback=None):
        '''Fetch a file listing.

        Returns:
            .ftp.request.ListingResponse

        Coroutine.
        '''
        response = ListingResponse()

        yield From(self._prepare_fetch(request, response, file, callback))

        try:
            try:
                reply = yield From(self._get_machine_listing())
            except FTPServerError as error:
                response.body.seek(0)
                response.body.truncate()
                if error.reply_code in (ReplyCodes.syntax_error_command_unrecognized,
                                        ReplyCodes.command_not_implemented):
                    reply = yield From(self._get_list_listing())
                else:
                    raise
        except ListingError as error:
            raise ProtocolError(*error.args) from error

        self._clean_up_fetch(reply)

        raise Return(response)

    @trollius.coroutine
    def _prepare_fetch(self, request, response, file=None, callback=None):
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

        if callback:
            file = callback(request, response)

        if not isinstance(file, Body):
            self._response.body = Body(file)
        else:
            self._response.body = file

    def _clean_up_fetch(self, reply):
        '''Clean up after a fetch.'''
        self._response.body.seek(0)
        self._response.reply = reply

        if self._recorder_session:
            self._recorder_session.end_control(self._response)

    @trollius.coroutine
    def _fetch_with_command(self, command, file=None):
        '''Fetch data through a data connection.

        Coroutine.
        '''
        # TODO: the recorder needs to fit inside here
        data_connection = None
        data_stream = None

        @trollius.coroutine
        def connection_factory(address):
            nonlocal data_connection
            data_connection = yield From(
                self._connection_pool.check_out(address[0], address[1]))
            raise Return(data_connection)

        try:
            data_stream = yield From(self._commander.setup_data_stream(
                connection_factory
            ))

            if self._recorder_session:
                self._response.data_address = data_connection.address
                self._recorder_session.pre_response(self._response)

                def data_callback(action, data):
                    if action == 'read':
                        self._recorder_session.response_data(data)

                data_stream.data_observer.add(data_callback)

            reply = yield From(self._commander.read_stream(
                command, file, data_stream
            ))

            if self._recorder_session:
                self._recorder_session.response(self._response)

            raise Return(reply)
        finally:
            if data_stream:
                data_stream.data_observer.clear()

            if data_connection:
                data_connection.close()
                self._connection_pool.check_in(data_connection)

    @trollius.coroutine
    def _get_machine_listing(self):
        '''Request a MLSD.

        Coroutine.
        '''
        reply = yield From(self._fetch_with_command(
            Command('MLSD', self._request.url_info.path), self._response.body
        ))

        if self._response.body.tell() == 0:
            listings = ()
        else:
            self._response.body.seek(0)

            listings = wpull.ftp.util.parse_machine_listing(
                self._response.body.read().decode('latin-1'),
                convert=True, strict=False
                )

        self._response.files = listings

        raise Return(reply)

    @trollius.coroutine
    def _get_list_listing(self):
        '''Request a LIST listing.

        Coroutine.
        '''
        reply = yield From(self._fetch_with_command(
            Command('LIST', self._request.url_info.path), self._response.body
        ))

        if self._response.body.tell() == 0:
            listings = ()
        else:
            self._response.body.seek(0)

            file = io.TextIOWrapper(self._response.body, encoding='latin-1')

            listing_parser = ListingParser(file=file)
            listing_parser.run_heuristics()

            listings = listing_parser.parse()

            # We don't want the file to be closed when exiting this function
            file.detach()

        self._response.files = listings

        raise Return(reply)

    def clean(self):
        if self._connection:
            self._connection_pool.check_in(self._connection)

    def close(self):
        if self._connection:
            self._connection.close()
