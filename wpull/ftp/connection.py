# encoding=utf-8
'''FTP Connection.'''
import tornado.gen

from wpull.conversation import BaseConnection
from wpull.network import Resolver


class Connection(BaseConnection):
    '''Represents the FTP control and data connection.'''
    def __init__(self, address, resolver=None):
        super().__init__(address, resolver=resolver)
        self._control_io_stream = None
        self._data_io_stream = None

#     @tornado.gen.coroutine
#     def fetch(self, request, recorder=None, pre_response_callback=None):
#         yield self._resolve_address()

    @tornado.gen.coroutine
    def connect_data_connection(self):
        pass

    def connected(self):
        if self._control_io_stream and not self._control_io_stream.closed():
            return True
        if self._data_io_stream and not self._data_io_stream.closed():
            return True

    def close(self):
        if self._control_io_stream:
            self._control_io_stream.close()

        if self._data_io_stream:
            self._data_io_stream.close()

    @tornado.gen.coroutine
    def _connect(self):
        '''Connect the socket if not already connected.'''
        if self.connected():
            return

        yield self._resolve_address()
        self._make_socket_and_io_stream()
        yield self._connect_io_stream(
            self._resolved_address, self._control_io_stream
        )

    def _make_socket_and_io_stream(self):
        socket_obj = self._new_socket()
        self._control_io_stream = self._new_iostream(socket_obj)
