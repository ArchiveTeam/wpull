'''FTP client.'''
from trollius import From, Return
import trollius

from wpull.abstract.client import BaseClient, BaseSession
from wpull.body import Body
from wpull.ftp.command import Commander
from wpull.ftp.request import Response, Command
from wpull.ftp.stream import ControlStream


class Client(BaseClient):
    '''FTP Client.

    The session object is :class:`Session`.
    '''
    def _session_class(self):
        return Session


class Session(BaseSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # TODO: recorder

    @trollius.coroutine
    def fetch(self, request):
        # TODO: need to split this into fetch and read content like in the
        # http client
        session = yield From(
            self._connection_pool.session(
                request.url_info.hostname, request.url_info.port
            ))

        with session as connection:
            control_stream = ControlStream(connection)
            commander = Commander(control_stream)
            # TODO: grab defaults from options
            username = request.url_info.username or 'anonymous'
            password = request.url_info.password or 'wpull'
            response = Response()
            response.body = Body()

            yield From(commander.reconnect())
            yield From(commander.login(username, password))

            data_connection = None

            @trollius.coroutine
            def connection_factory(address):
                nonlocal data_connection
                data_connection = yield From(
                    self._connection_pool.check_out(address[0], address[1]))
                raise Return(data_connection)

            try:
                yield From(commander.get_file(
                    Command('RETR', request.url_info.path),
                    response.body,
                    connection_factory
                ))
            finally:
                if data_connection:
                    data_connection.close()
                    self._connection_pool.check_in(data_connection)

            response.body.seek(0)

        return response

    @trollius.coroutine
    def file_listing(self, arg):
        # TODO:
        pass

    def clean(self):
        pass

    def close(self):
        pass
