# encoding=utf-8
'''Extended subclasses.'''
import datetime
import logging
import tornado.iostream
import toro

from wpull.errors import NetworkError, SSLVerficationError
import wpull.util


_logger = logging.getLogger(__name__)


class BaseIOStream(object):
    '''Tornado IOStream with timeouts.

    Args:
        connect_timeout: A time in seconds to time out connecting
        read_timeout: A time in seconds to time out reading
    '''
    def __init__(self, *args, **kwargs):
        self._connect_timeout = kwargs.pop('connect_timeout', None)
        self._read_timeout = kwargs.pop('read_timeout', None)
        super().__init__(*args, **kwargs)


class IOStreamMixin(object):
    @property
    def buffer_full(self):
        '''Return whether the buffer is full.'''
        return self._read_buffer_size >= self.max_buffer_size

    @tornado.gen.coroutine
    def connect_gen(self, address, server_hostname):
        '''Connect with timeout.

        Raises:
            :class:`.errors.NetworkError`
        '''
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
        '''Read with timeout.

        Raises:
            :class:`.errors.NetworkError`
        '''
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
            raise NetworkError('Read timed out.') from error
        else:
            raise tornado.gen.Return(result)

    def read_with_queue(self, func_name, *args, **kwargs):
        '''Read with timeout and queue.'''
        if self._read_timeout:
            deadline = datetime.timedelta(seconds=self._read_timeout)
        else:
            deadline = None

        stream_queue = StreamQueue(deadline=deadline)

        def callback(data):
            stream_queue.put_nowait(None)

        def stream_callback(data):
            stream_queue.put_nowait(data)

        getattr(self.super, func_name)(
            self,
            *args,
            callback=callback,
            streaming_callback=stream_callback,
            **kwargs
        )

        return stream_queue

    @tornado.gen.coroutine
    def connect(self, address, server_hostname):
        '''Connect.'''
        yield self.connect_gen(address, server_hostname)

    @tornado.gen.coroutine
    def read_bytes(self, num_bytes, streaming_callback=None):
        '''Read bytes.'''
        raise tornado.gen.Return((
            yield self.read_gen(
                'read_bytes', num_bytes, streaming_callback=streaming_callback)
        ))

    def read_bytes_queue(self, num_bytes):
        '''Read bytes with queue.'''
        return self.read_with_queue('read_bytes', num_bytes)

    @tornado.gen.coroutine
    def read_until(self, delimiter):
        '''Read until.'''
        raise tornado.gen.Return((
            yield self.read_gen('read_until', delimiter)
        ))

    @tornado.gen.coroutine
    def read_until_close(self, streaming_callback=None):
        '''Read until close.'''
        raise tornado.gen.Return((
            yield self.read_gen(
                'read_until_close', streaming_callback=streaming_callback)
        ))

    def read_until_close_queue(self):
        '''Read until close with queue.'''
        return self.read_with_queue('read_until_close')

    @tornado.gen.coroutine
    def read_until_regex(self, regex):
        '''Read until regex.'''
        raise tornado.gen.Return((
            yield self.read_gen('read_until_regex', regex)
        ))


class IOStream(BaseIOStream, tornado.iostream.IOStream, IOStreamMixin):
    '''IOStream.'''
    @property
    def super(self):
        return tornado.iostream.IOStream

    connect = IOStreamMixin.connect
    read_bytes = IOStreamMixin.read_bytes
    read_until = IOStreamMixin.read_until
    read_until_close = IOStreamMixin.read_until_close
    read_until_regex = IOStreamMixin.read_until_regex


class SSLIOStream(BaseIOStream, tornado.iostream.SSLIOStream, IOStreamMixin):
    '''SSLIOStream.'''
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


class StreamQueue(toro.Queue):
    def __init__(self, maxsize=0, io_loop=None, deadline=None):
        toro.Queue.__init__(self, maxsize, io_loop)
        self._deadline = deadline

    @tornado.gen.coroutine
    def get(self, deadline=None):
        try:
            result = yield toro.Queue.get(self, deadline or self._deadline)
        except toro.Timeout as error:
            raise NetworkError('Read timed out.') from error

        raise tornado.gen.Return(result)
