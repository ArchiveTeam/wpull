# encoding=utf-8
import logging
import tornado.iostream

from wpull.errors import NetworkError, SSLVerficationError
import wpull.util


_logger = logging.getLogger(__name__)


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
    def connect_gen(self, address, server_hostname):
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
            self.close()
            raise NetworkError('Connection timed out') from error

    @tornado.gen.coroutine
    def read_gen(self, func_name, *args, **kwargs):
        @tornado.gen.coroutine
        def read():
            result = yield tornado.gen.Task(
                getattr(self.super, func_name),
                self,
                *args,
                **kwargs
            )
            raise tornado.gen.Return(result)
        try:
            result = yield wpull.util.wait_future(read(), self._read_timeout)
        except wpull.util.TimedOut as error:
            self.close()
            raise NetworkError('Read timed out') from error
        else:
            raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def connect(self, address, server_hostname):
        yield self.connect_gen(address, server_hostname)

    @tornado.gen.coroutine
    def read_bytes(self, num_bytes, streaming_callback=None):
        raise tornado.gen.Return((
            yield self.read_gen(
                'read_bytes', num_bytes, streaming_callback=streaming_callback)
        ))

    @tornado.gen.coroutine
    def read_until(self, delimiter):
        raise tornado.gen.Return((
            yield self.read_gen('read_until', delimiter)
        ))

    @tornado.gen.coroutine
    def read_until_close(self, streaming_callback=None):
        raise tornado.gen.Return((
            yield self.read_gen(
                'read_until_close', streaming_callback=streaming_callback)
        ))

    @tornado.gen.coroutine
    def read_until_regex(self, regex):
        raise tornado.gen.Return((
            yield self.read_gen('read_until_regex', regex)
        ))


class IOStream(BaseIOStream, tornado.iostream.IOStream, IOStreamMixin):
    @property
    def super(self):
        return tornado.iostream.IOStream

    connect = IOStreamMixin.connect
    read_bytes = IOStreamMixin.read_bytes
    read_until = IOStreamMixin.read_until
    read_until_close = IOStreamMixin.read_until_close
    read_until_regex = IOStreamMixin.read_until_regex


class SSLIOStream(BaseIOStream, tornado.iostream.SSLIOStream, IOStreamMixin):
    @property
    def super(self):
        return tornado.iostream.SSLIOStream

    connect = IOStreamMixin.connect
    read_bytes = IOStreamMixin.read_bytes
    read_until = IOStreamMixin.read_until
    read_until_close = IOStreamMixin.read_until_close
    read_until_regex = IOStreamMixin.read_until_regex

    def _do_ssl_handshake(self):
        _logger.debug('Do SSL handshake.')
        return super()._do_ssl_handshake()

    def _verify_cert(self, peercert):
        result = super()._verify_cert(peercert)
        _logger.debug('Verify cert ok={0}.'.format(result))

        if not result:
            raise SSLVerficationError('Invalid SSL certificate')

        return result

    def _handle_connect(self):
        _logger.debug('Handle connect. Wrap socket.')
        return super()._handle_connect()
