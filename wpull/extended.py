import tornado.iostream

from wpull.errors import NetworkError
import wpull.util


class BaseIOStream(object):
    def __init__(self, *args, **kwargs):
        self._connect_timeout = kwargs.pop('connect_timeout', None)
        self._read_timeout = kwargs.pop('read_timeout', None)
        super().__init__(*args, **kwargs)


class IOStreamMixin(object):
    @property
    def buffer_full(self):
        return self._read_buffer_size >= self.max_buffer_size

    @tornado.gen.coroutine
    def connect_gen(self, address, server_hostname=None):
        @tornado.gen.coroutine
        def connect():
            yield tornado.gen.Task(
                self.super.connect,
                self,
                address,
                server_hostname=server_hostname
            )

        try:
            yield wpull.util.wait_future(connect(), self._connect_timeout)
        except wpull.util.TimedOut as error:
            raise NetworkError('Connection timed out') from error


class IOStream(BaseIOStream, tornado.iostream.IOStream, IOStreamMixin):
    @property
    def super(self):
        return tornado.iostream.IOStream

    @tornado.gen.coroutine
    def connect(self, address, server_hostname=None):
        yield self.connect_gen(address, server_hostname)


class SSLIOStream(BaseIOStream, tornado.iostream.SSLIOStream, IOStreamMixin):
    @property
    def super(self):
        return tornado.iostream.SSLIOStream

    @tornado.gen.coroutine
    def connect(self, address, server_hostname=None):
        yield self.connect_gen(address, server_hostname)
