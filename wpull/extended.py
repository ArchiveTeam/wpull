import tornado.iostream


class IOStreamMixin():
    @property
    def buffer_full(self):
        return self._read_buffer_size >= self.max_buffer_size


class IOStream(tornado.iostream.IOStream, IOStreamMixin):
    pass


class SSLIOStream(tornado.iostream.SSLIOStream, IOStreamMixin):
    pass
