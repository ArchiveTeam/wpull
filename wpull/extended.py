import tornado.iostream

import wpull.util


class IOStreamMixin():
    @property
    def buffer_full(self):
        return self._read_buffer_size >= self.max_buffer_size

    @tornado.gen.coroutine
    def connect_gen(self, address, server_hostname=None, timeout=None):
        @tornado.gen.coroutine
        def connect():
            yield tornado.gen.Task(
                self.connect, address, server_hostname=server_hostname)

        yield wpull.util.wait_future(connect(), timeout)


class IOStream(tornado.iostream.IOStream, IOStreamMixin):
    pass


class SSLIOStream(tornado.iostream.SSLIOStream, IOStreamMixin):
    pass
