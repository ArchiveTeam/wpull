# encoding=utf-8
'''HTTP connection handling.'''
import collections
import errno
import gettext
import http.client
import itertools
import logging
import re
import socket
import ssl
import sys
import tornado.gen
from tornado.iostream import StreamClosedError
import toro
import traceback
import zlib

from wpull.actor import Event
from wpull.errors import (SSLVerficationError, ConnectionRefused, NetworkError,
    ProtocolError)
from wpull.iostream import SSLIOStream, IOStream
from wpull.http.request import Response
from wpull.network import Resolver


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Connection(object):
    '''A single HTTP connection.

    Args:
        host: The hostname
        port: The port number
        ssl: If True, SSL is used
        bind_address: The IP address to bind the socket. Must match
            :func:`socket.SocketType.bind`. Use this if your local host has
            multiple IP addresses.
        resolver: :class:`.network.Resovler`
        connect_timeout: If given, the time in seconds before the connection
            is timed out during connection. Otherwise, depend on the
            underlying libraries for timeout.
        read_timeout: If given, the time in seconds before the connection
            is timed out during reads. Otherwise, depend on the
            underlying libraries for timeout.
        keep_alive: If True, use HTTP keep-alive.
        ssl_options: A ``dict`` containing options for :func:`ssl.wrap_socket`
    '''
    class ConnectionEvents(object):
        def __init__(self):
            self.pre_request = Event()
            self.request = Event()
            self.pre_response = Event()
            self.response = Event()
            self.request_data = Event()
            self.response_data = Event()

        def attach(self, recorder_session):
            self.pre_request.handle(recorder_session.pre_request)
            self.request.handle(recorder_session.request)
            self.pre_response.handle(recorder_session.pre_response)
            self.response.handle(recorder_session.response)
            self.request_data.handle(recorder_session.request_data)
            self.response_data.handle(recorder_session.response_data)

        def clear(self):
            self.pre_request.clear()
            self.request.clear()
            self.pre_response.clear()
            self.response.clear()
            self.request_data.clear()
            self.response_data.clear()

    DEFAULT_BUFFER_SIZE = 10485760
    '''Default buffer size in bytes.'''
    DEFAULT_NO_CONTENT_CODES = frozenset(itertools.chain(
        range(100, 200),
        [http.client.NO_CONTENT, http.client.NOT_MODIFIED]
    ))
    '''Status codes where a response body is prohibited.'''

    def __init__(self, host, port, ssl=False, bind_address=None,
    resolver=None, connect_timeout=None, read_timeout=None,
    keep_alive=True, ssl_options=None, buffer_size=DEFAULT_BUFFER_SIZE,
    no_content_codes=DEFAULT_NO_CONTENT_CODES):
        self._host = host
        self._port = port
        self._ssl = ssl
        self._address = None
        self._socket = None
        self._io_stream = None
        self._bind_address = bind_address
        self._events = Connection.ConnectionEvents()
        self._resolver = resolver or Resolver()
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._keep_alive = keep_alive
        self._active = False
        self._ssl_options = ssl_options
        self._buffer_size = buffer_size
        self._gzip_decompressor = None
        self._no_content_codes = no_content_codes

    @tornado.gen.coroutine
    def _make_socket(self):
        '''Make and wrap the socket with an IOStream.'''
        family, self._address = yield self._resolver.resolve(
            self._host, self._port)
        self._socket = socket.socket(family, socket.SOCK_STREAM)

        _logger.debug('Socket to {0}/{1}.'.format(family, self._address))

        if self._bind_address:
            _logger.debug('Binding socket to {0}'.format(self._bind_address))
            self._socket.bind(self._bind_address)

        if self._ssl:
            self._io_stream = SSLIOStream(
                self._socket,
                max_buffer_size=self._buffer_size,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
                ssl_options=self._ssl_options,
            )
        else:
            self._io_stream = IOStream(
                self._socket,
                max_buffer_size=self._buffer_size,
                connect_timeout=self._connect_timeout,
                read_timeout=self._read_timeout,
            )

        self._io_stream.set_close_callback(self._stream_closed_callback)

    @tornado.gen.coroutine
    def _connect(self):
        '''Connect the socket if not already connected.'''
        if self.connected:
            # Reset the callback so the context does not leak to another
            self._io_stream.set_close_callback(self._stream_closed_callback)
            return

        yield self._make_socket()

        _logger.debug('Connecting to {0}.'.format(self._address))
        try:
            yield self._io_stream.connect(self._address, self._host)
        except (ssl.SSLError, tornado.netutil.SSLCertificateError,
        SSLVerficationError) as error:
            raise SSLVerficationError('SSLError: {error}'.format(
                error=error)) from error
        except socket.error as error:
            if error.errno == errno.ECONNREFUSED:
                raise ConnectionRefused('Connection refused: {error}'.format(
                    error=error)) from error
            else:
                raise NetworkError('Connection error: {error}'.format(
                    error=error)) from error
        else:
            _logger.debug('Connected.')
            self._connected = True

    @tornado.gen.coroutine
    def fetch(self, request, recorder=None, response_factory=Response):
        '''Fetch a document.

        Args:
            request: :class:`Request`
            recorder: :class:`.recorder.BaseRecorder`
            response_factory: a callable object that makes a :class:`Response`.

        If an exception occurs, this function will close the connection
        automatically.

        Returns:
            Response: An instance of :class:`Response`

        Raises:
            Exception: Exceptions specified in :mod:`.errors`.
        '''
        _logger.debug('Request {0}.'.format(request))

        assert not self._active

        self._active = True

        try:
            if recorder:
                with recorder.session() as recorder_session:
                    self._events.attach(recorder_session)
                    response = yield self._process_request(request,
                        response_factory)
            else:
                response = yield self._process_request(request,
                    response_factory)

            response.url_info = request.url_info
        except:
            _logger.debug('Fetch exception.')
            self.close()
            raise
        finally:
            self._events.clear()
            self._active = False

        if not self._keep_alive:
            _logger.debug('Closing connection.')
            self.close()

        _logger.debug('Fetching done.')

        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _process_request(self, request, response_factory):
        '''Fulfill a single request.

        Returns:
            Response
        '''
        yield self._connect()

        request.address = self._address
        self._events.pre_request(request)

        if sys.version_info < (3, 3):
            error_class = (socket.error, StreamClosedError)
        else:
            error_class = (ConnectionError, StreamClosedError)

        try:
            yield self._send_request_header(request)
            yield self._send_request_body(request)
            self._events.request.fire(request)

            response = yield self._read_response_header(response_factory)
            # TODO: handle 100 Continue

            yield self._read_response_body(request, response)
        except error_class as error:
            raise NetworkError('Network error: {0}'.format(error)) from error

        self._events.response.fire(response)

        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _send_request_header(self, request):
        '''Send the request's HTTP status line and header fields.'''
        _logger.debug('Sending headers.')
        data = request.header()
        self._events.request_data.fire(data)
        yield self._io_stream.write(data)

    @tornado.gen.coroutine
    def _send_request_body(self, request):
        '''Send the request's content body.'''
        _logger.debug('Sending body.')
        for data in request.body or ():
            self._events.request_data.fire(data)
            yield self._io_stream.write(data)

    @tornado.gen.coroutine
    def _read_response_header(self, response_factory):
        '''Read the response's HTTP status line and header fields.'''
        _logger.debug('Reading header.')
        response_header_data = yield self._io_stream.read_until_regex(
            br'\r?\n\r?\n')

        self._events.response_data.fire(response_header_data)

        status_line, header = response_header_data.split(b'\n', 1)
        version, status_code, status_reason = Response.parse_status_line(
            status_line)
        response = response_factory(version, status_code, status_reason)
        response.fields.parse(header, strict=False)
        self._events.pre_response.fire(response)

        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _read_response_body(self, request, response):
        '''Read the response's content body.'''
        if 'Content-Length' not in response.fields \
        and 'Transfer-Encoding' not in response.fields \
        and (
            response.status_code in self._no_content_codes \
            or request.method.upper() == 'HEAD'
        ):
            return

        self._setup_decompressor(response)

        if re.match(r'chunked($|;)',
        response.fields.get('Transfer-Encoding', '')):
            yield self._read_response_by_chunk(response)
        elif 'Content-Length' in response.fields:
            yield self._read_response_by_length(response)
        else:
            yield self._read_response_until_close(response)

        response.body.content_file.seek(0)

    def _setup_decompressor(self, response):
        '''Set up the content encoding decompressor.'''
        gzipped = response.fields.get('Content-Encoding') == 'gzip'

        if gzipped:
            self._gzip_decompressor = tornado.util.GzipDecompressor()
        else:
            self._gzip_decompressor = None

    def _decompress_data(self, data):
        '''Decompress the given data and return the uncompressed data.'''
        if self._gzip_decompressor:
            try:
                return self._gzip_decompressor.decompress(data)
            except zlib.error as error:
                raise ProtocolError(
                    'zlib error: {0}.'.format(error)
                ) from error
        else:
            return data

    def _flush_decompressor(self):
        '''Return any data left in the decompressor.'''
        if self._gzip_decompressor:
            try:
                return self._gzip_decompressor.flush()
            except zlib.error as error:
                raise ProtocolError(
                    'zlib flush error: {0}.'.format(error)
                ) from error
        else:
            return b''

    @tornado.gen.coroutine
    def _read_response_by_length(self, response):
        '''Read the connection specified by a length.'''
        _logger.debug('Reading body by length.')

        try:
            body_size = int(response.fields['Content-Length'])

            if body_size < 0:
                raise ValueError('Content length cannot be negative.')

        except ValueError as error:
            _logger.warning(
                _('Invalid content length: {error}').format(error=error)
            )

            yield self._read_response_until_close(response)
            return

        data_queue = self._io_stream.read_bytes_queue(body_size)

        while True:
            data = yield data_queue.get()

            if data is None:
                break

            self._events.response_data.fire(data)
            response.body.content_file.write(self._decompress_data(data))

        response.body.content_file.write(self._flush_decompressor())

    @tornado.gen.coroutine
    def _read_response_by_chunk(self, response):
        '''Read the connection using chunked transfer encoding.'''
        stream_reader = ChunkedTransferStreamReader(self._io_stream)
        stream_reader.data_event.handle(self._events.response_data.fire)
        stream_reader.content_event.handle(
            lambda data:
                response.body.content_file.write(self._decompress_data(data))
        )

        while True:
            chunk_size = yield stream_reader.read_chunk()

            if chunk_size == 0:
                break

        trailer_data = yield stream_reader.read_trailer()
        response.fields.parse(trailer_data)

        response.body.content_file.write(self._flush_decompressor())

    @tornado.gen.coroutine
    def _read_response_until_close(self, response):
        '''Read the response until the connection closes.'''
        _logger.debug('Reading body until close.')

        data_queue = self._io_stream.read_until_close_queue()

        while True:
            data = yield data_queue.get()

            if data is None:
                break

            self._events.response_data.fire(data)
            response.body.content_file.write(self._decompress_data(data))

        response.body.content_file.write(self._flush_decompressor())

    @property
    def active(self):
        '''Return whether the connection is in use due to a fetch in progress.
        '''
        return self._active

    @property
    def connected(self):
        '''Return whether the connection is connected.'''
        return self._io_stream and not self._io_stream.closed()

    def close(self):
        '''Close the connection if open.'''
        if self._io_stream:
            self._io_stream.close()

    def _stream_closed_callback(self):
        _logger.debug('Stream closed. '
            'active={0} connected={1} ' \
            'closed={2} reading={3} writing={3}'.format(
                self._active,
                self.connected,
                self._io_stream.closed(),
                self._io_stream.reading(),
                self._io_stream.writing())
        )

        if not self._active:
            # We are likely in a context that's already dead
            _logger.debug('Ignoring stream closed error={0}.'\
                .format(self._io_stream.error))
            return

        if self._io_stream.error:
            _logger.debug('Throwing error {0}.'.format(self._io_stream.error))
            raise self._io_stream.error

        if self._io_stream.buffer_full:
            _logger.debug('Buffer full.')
            raise ProtocolError('Buffer full.')


class ChunkedTransferStreamReader(object):
    '''Read chunked transfer encoded stream.

    Args:
        io_stream: An instance of :class:`.extended.IOStream`.

    Attributes:
        data_event (Event): An instance of :class:`.actor.Event` that will
            be fired when raw data is read from the stream.
        content_event (Event): An instance of :class:`.actor.Event` that will
            be fired when content data is decoded from the stream.
    '''
    def __init__(self, io_stream):
        self._io_stream = io_stream
        self.data_event = Event()
        self.content_event = Event()

    @tornado.gen.coroutine
    def read_chunk(self):
        '''Read a single chunk of the chunked transfer encoding.

        Returns:
            int: The size of the content in the chunk.
        '''
        _logger.debug('Reading chunk.')
        chunk_size_hex = yield self._io_stream.read_until_regex(b'[^\n\r]+')

        self.data_event.fire(chunk_size_hex)

        try:
            chunk_size = int(chunk_size_hex.split(b';', 1)[0].strip(), 16)
        except ValueError as error:
            raise ProtocolError(error.args[0]) from error

        _logger.debug('Getting chunk size={0}.'.format(chunk_size))

        if not chunk_size:
            raise tornado.gen.Return(chunk_size)

        newline_data = yield self._io_stream.read_until(b'\n')

        self.data_event.fire(newline_data)

        data_queue = self._io_stream.read_bytes_queue(chunk_size)

        while True:
            data = yield data_queue.get()

            if data is None:
                break

            self.data_event.fire(data)
            self.content_event.fire(data)

        raise tornado.gen.Return(chunk_size)

    @tornado.gen.coroutine
    def read_trailer(self):
        '''Read the HTTP trailer fields.

        Returns:
            bytes: The trailer data.
        '''
        _logger.debug('Reading chunked trailer.')
        trailer_data = yield self._io_stream.read_until_regex(br'\r?\n\r?\n')

        self.data_event.fire(trailer_data)

        raise tornado.gen.Return(trailer_data)


class HostConnectionPool(collections.Set):
    '''A Connection pool to a particular server.'''
    def __init__(self, host, port, request_queue=None, ssl=False, max_count=6,
    connection_factory=Connection):
        assert isinstance(host, str)
        assert isinstance(port, int) and port
        self._host = host
        self._port = port
        self._request_queue = toro.Queue()
        self._ssl = ssl
        self._connection_factory = connection_factory
        self._connections = set()
        self._max_count = max_count
        self._max_count_semaphore = toro.BoundedSemaphore(max_count)
        self._running = True
        self._cleaner_timer = tornado.ioloop.PeriodicCallback(
            self.clean, 300000)
        self._run()
        self._cleaner_timer.start()

    @property
    def active(self):
        '''Return whether connections are active or items are queued.'''
        for connection in self._connections:
            if connection.active:
                return True

        return self._request_queue.qsize() > 0

    @tornado.gen.coroutine
    def put(self, request, kwargs, async_result):
        '''Put a request into the queue.'''
        _logger.debug('Host pool queue request {0}'.format(request))
        assert self._running
        yield self._request_queue.put((request, kwargs, async_result))

    @tornado.gen.coroutine
    def _run(self):
        while self._running or self._request_queue.qsize():
            _logger.debug('Host pool running ({0}:{1} SSL={2}).'.format(
                self._host, self._port, self._ssl))
            yield self._max_count_semaphore.acquire()

            tornado.ioloop.IOLoop.current().add_future(
                self._process_request_wrapper(),
                lambda future: future.result()
            )

    @tornado.gen.coroutine
    def _process_request_wrapper(self):
        try:
            yield self._process_request()
            self._max_count_semaphore.release()
            _logger.debug('Host pool semaphore released.')
        except:
            _logger.exception('Fatal error processing request.')
            sys.exit('Fatal error.')

    @tornado.gen.coroutine
    def _process_request(self):
        request, kwargs, async_result = yield self._request_queue.get()

        _logger.debug('Host pool got request {0}'.format(request))

        connection = self._get_ready_connection()

        try:
            response = yield connection.fetch(request, **kwargs)
        except Exception as error:
            _logger.debug('Host pool got an error from fetch: {error}'\
                .format(error=error))
            _logger.debug(traceback.format_exc())
            async_result.set(error)
        else:
            async_result.set(response)

        _logger.debug('Host pool done {0}'.format(request))

    def _get_ready_connection(self):
        _logger.debug('Getting a connection.')

        for connection in self._connections:
            if not connection.active:
                _logger.debug('Found a unused connection.')
                return connection

        if len(self._connections) < self._max_count:
            _logger.debug('Making another connection.')
            connection = self._connection_factory(
                self._host, self._port, ssl=self._ssl)
            self._connections.add(connection)
            return connection

        _logger.debug('Connections len={0} max={1}'.format(
            len(self._connections), self._max_count))

        raise Exception('Impossibly ran out of unused connections.')

    def __contains__(self, key):
        return key in self._connections

    def __iter__(self):
        return iter(self._connections)

    def __len__(self):
        return len(self._connections)

    def stop(self):
        '''Stop the workers.'''
        self._running = False
        self._cleaner_timer.stop()

    def close(self):
        '''Stop workers, close all the connections and remove them.'''
        self.stop()

        for connection in self._connections:
            _logger.debug('Closing {0}.'.format(connection))
            connection.close()

        self._connections.clear()

    def clean(self, force_close=False):
        '''Remove connections not in use.'''
        for connection in tuple(self._connections):
            if not connection.active \
            and (force_close or not connection.connected):
                connection.close()
                self._connections.remove(connection)
                _logger.debug('Cleaned connection {0}'.format(connection))


class ConnectionPool(collections.Mapping):
    '''A pool of HostConnectionPool.'''
    def __init__(self, host_connection_pool_factory=HostConnectionPool):
        self._pools = {}
        self._host_connection_pool_factory = host_connection_pool_factory

    @tornado.gen.coroutine
    def put(self, request, kwargs, async_result):
        '''Put a request into the queue.'''
        _logger.debug('Connection pool queue request {0}'.format(request))

        if request.address:
            address = request.address
        else:
            host = request.url_info.hostname
            port = request.url_info.port
            address = (host, port)
            ssl = (request.url_info.scheme == 'https')

        if address not in self._pools:
            _logger.debug('New host pool.')
            self._pools[address] = self._host_connection_pool_factory(
                host, port, ssl=ssl)

        yield self._pools[address].put(request, kwargs, async_result)

    def __getitem__(self, key):
        return self._pools[key]

    def __iter__(self):
        return iter(self._pools)

    def __len__(self):
        return len(self._pools)

    def close(self):
        '''Close all the Host Connection Pools and remove them.'''
        for key in self._pools:
            _logger.debug('Closing pool for {0}.'.format(key))
            self._pools[key].close()

        self._pools.clear()

    def clean(self):
        '''Remove Host Connection Pools not in use.'''
        for key in tuple(self._pools.keys()):
            pool = self._pools[key]

            pool.clean()

            if not pool.active:
                pool.stop()
                del self._pools[key]
                _logger.debug('Cleaned host pool {0}.'.format(pool))
