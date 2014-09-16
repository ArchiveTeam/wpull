'''FTP client.'''
import io

from trollius import From, Return
import trollius

from wpull.abstract.client import BaseClient, BaseSession
from wpull.body import Body
from wpull.ftp.command import Commander
from wpull.ftp.ls.parse import ListingParser
from wpull.ftp.request import Response, Command, ListingResponse
from wpull.ftp.stream import ControlStream
from wpull.ftp.util import FTPServerError
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

        # TODO: recorder
        # TODO: maybe keep track of sessions among connections to avoid
        # having to login over and over again

    @trollius.coroutine
    def _init_stream(self, request):
        '''Create streams and commander.

        Coroutine.
        '''
        assert not self._connection
        self._connection = yield From(self._connection_pool.check_out(
            request.url_info.hostname, request.url_info.port))
        self._control_stream = ControlStream(self._connection)
        self._commander = Commander(self._control_stream)
        self._request = request

    @trollius.coroutine
    def _log_in(self):
        '''Connect and login.

        Coroutine.
        '''
        # TODO: grab defaults from options
        username = self._request.url_info.username or 'anonymous'
        password = self._request.url_info.password or 'wpull'

        yield From(self._commander.reconnect())
        yield From(self._commander.login(username, password))

    @trollius.coroutine
    def fetch(self, request, file):
        '''Fetch a file.

        Returns:
            .ftp.request.Response

        Coroutine.
        '''
        yield From(self._init_stream(request))
        yield From(self._log_in())

        response = Response()
        response.request = request

        if not isinstance(file, Body):
            response.body = Body(file)
        else:
            response.body = file

        yield From(self._fetch_with_command(
            Command('RETR', request.url_info.path), response.body
        ))

        response.body.seek(0)

        raise Return(response)

    @trollius.coroutine
    def fetch_file_listing(self, request, file):
        '''Fetch a file listing.

        Returns:
            .ftp.request.ListingResponse

        Coroutine.
        '''
        yield From(self._init_stream(request))
        yield From(self._log_in())

        response = ListingResponse()
        response.request = request

        if not isinstance(file, Body):
            response.body = Body(file)
        else:
            response.body = file

        try:
            yield From(self._get_machine_listing(request, response))
        except FTPServerError as error:
            response.body.seek(0)
            response.body.truncate()
            if error.reply_code in (500, 502):
                yield From(self._get_list_listing(request, response))
            else:
                raise

        response.body.seek(0)

        raise Return(response)

    @trollius.coroutine
    def _fetch_with_command(self, command, file=None):
        '''Fetch data through a data connection.

        Coroutine.
        '''
        data_connection = None

        @trollius.coroutine
        def connection_factory(address):
            nonlocal data_connection
            data_connection = yield From(
                self._connection_pool.check_out(address[0], address[1]))
            raise Return(data_connection)

        try:
            yield From(self._commander.get_file(
                command,
                file,
                connection_factory
            ))
        finally:
            if data_connection:
                data_connection.close()
                self._connection_pool.check_in(data_connection)

    @trollius.coroutine
    def _get_machine_listing(self, request, response):
        '''Request a MLSD.

        Coroutine.
        '''
        yield From(self._fetch_with_command(
            Command('MLSD', request.url_info.path), response.body
        ))

        response.body.seek(0)

        listings = wpull.ftp.util.parse_machine_listing(
            response.body.read().decode('latin-1'),
            convert=True, strict=False
            )

        response.files = listings

    @trollius.coroutine
    def _get_list_listing(self, request, response):
        '''Request a LIST listing.

        Coroutine.
        '''
        yield From(self._fetch_with_command(
            Command('LIST', request.url_info.path), response.body
        ))

        response.body.seek(0)

        file = io.TextIOWrapper(response.body, encoding='latin-1')

        listing_parser = ListingParser(file=file)
        listing_parser.run_heuristics()

        listings = listing_parser.parse()

        # We don't want the file to be closed when exiting this function
        file.detach()

        response.files = listings

    def clean(self):
        if self._connection:
            self._connection_pool.check_in(self._connection)

    def close(self):
        if self._connection:
            self._connection.close()
