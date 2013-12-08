import abc
import collections
import gettext
import gzip
import itertools
import logging
import queue
import re
import shutil
import socket
import tempfile
import tornado.gen
import toro

from wpull.actor import Event
from wpull.errors import ProtocolError, NetworkError
from wpull.extended import SSLIOStream, IOStream
from wpull.namevalue import NameValueRecord
from wpull.network import Resolver
from wpull.url import URLInfo
from wpull.util import to_str
import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class Request(object):
    def __init__(self, method, resource_url, version='HTTP/1.1'):
        self.method = method
        self.resource_url = resource_url
        self.url_info = None
        self.version = version
        self.fields = NameValueRecord()
        self.body = None

    @classmethod
    def new(cls, url, method='GET'):
        url_info = URLInfo.parse(url)
        resource_path = url_info.path

        if url_info.query:
            resource_path += '?' + url_info.query

        request = Request(method, resource_path)
        request.url_info = url_info
        request.fields['Host'] = url_info.hostname

        return request

    def iter_header(self):
        yield '{0} {1} {2}\r\n'.format(
            self.method, self.resource_url, self.version).encode()
        yield bytes(self.fields)
        yield b'\r\n'

    def iter_body(self):
        if self.body:
            return iter(self.body)
        else:
            return ()

    def __bytes__(self):
        return b''.join(itertools.chain(
            self.iter_header(), self.iter_body()))

    def __repr__(self):
        return '<Request({method}, {url}, {version})>'.format(
            method=self.method, url=self.resource_url, version=self.version
        )


class Response(object):
    def __init__(self, version, status_code, status_reason):
        self.version = version
        self.status_code = status_code
        self.status_reason = status_reason
        self.fields = NameValueRecord()
        self.body = None

    @classmethod
    def parse_status_line(cls, string):
        match = re.match(
            br'(HTTP/1\.[01])[ \t]+([0-9]{1,3})[ \t]+([^\r\n]*)',
            string
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return to_str((groups[0], int(groups[1]), groups[2]))

        raise ProtocolError('Error parsing status line ‘{0}’'.format(string))

    def iter_header(self):
        yield '{0} {1} {2}\r\n'.format(
            self.version, self.status_code, self.status_reason).encode()
        yield bytes(self.fields)
        yield b'\r\n'

    def iter_body(self):
        if self.body:
            return iter(self.body)
        else:
            return ()

    def __bytes__(self):
        return b''.join(itertools.chain(
            self.iter_header(), self.iter_body()))

    def __repr__(self):
        return '<Response({version}, {code}, {reason})>'.format(
            version=self.version, code=self.status_code,
            reason=self.status_reason
        )


class Body(object, metaclass=abc.ABCMeta):
    def __init__(self):
        self.http_file = None
        self.content_file = None
        self._content_data = None

    def __iter__(self):
        if self.http_file:
            with wpull.util.reset_file_offset(self.http_file):
                while True:
                    data = self.http_file.read(4096)
                    if not data:
                        break
                    yield data

    @property
    def content(self):
        if not self._content_data:
            with wpull.util.reset_file_offset(self.content_file):
                self._content_data = self.content_file.read()

        return self._content_data

    @classmethod
    def new_temp_file(cls):
        return tempfile.SpooledTemporaryFile(max_size=4194304)

    @abc.abstractmethod
    def transform(self):
        pass


class RequestBody(Body):
    def __init__(self, content_file):
        super().__init__()
        self.content_file = content_file
        self.http_file = content_file
        # TODO: support gzipping the content

    def transform(self):
        raise NotImplementedError()


class ResponseBody(Body):
    def __init__(self, http_file):
        super().__init__()
        self.http_file = http_file
        self.content_file = http_file

    def transform(self, chunked=False, gzipped=False):
        if chunked:
            self.content_file = decode_chunked_transfer(self.http_file)

        if gzipped:
            with wpull.util.reset_file_offset(self.content_file):
                with gzip.open(self.content_file) as in_file:
                    self.content_file = self.new_temp_file()
                    shutil.copyfileobj(in_file, self.content_file)


class Connection(object):
    # TODO: implement timeouts
    class ConnectionEvents(object):
        def __init__(self):
            self.request = Event()
            self.response = Event()
            self.request_data = Event()
            self.response_data = Event()

        def attach(self, recorder_session):
            self.request += recorder_session.request
            self.response += recorder_session.response
            self.request_data += recorder_session.request_data
            self.response_data += recorder_session.response_data

        def clear(self):
            self.request.clear()
            self.response.clear()
            self.request_data.clear()
            self.response_data.clear()

    DEFAULT_BUFFER_SIZE = 1048576

    def __init__(self, host, port, ssl=False, bind_address=None,
    resolver=None):
        self._host = host
        self._port = port
        self._ssl = ssl
        self._address = None
        self._socket = None
        self._io_stream = None
        self._bind_address = bind_address
        self._connected = False
        self._events = Connection.ConnectionEvents()
        self._resolver = resolver or Resolver()

    @tornado.gen.coroutine
    def _make_socket(self):
        family, self._address = yield self._resolver.resolve(
            self._host, self._port)
        self._socket = socket.socket(family, socket.SOCK_STREAM)

        _logger.debug('Socket to {0}/{1}.'.format(family, self._address))

        if self._bind_address:
            _logger.debug('Binding socket to {0}'.format(self._server_address))
            self._socket.bind(self._bind_address)

        if self._ssl:
            self._io_stream = SSLIOStream(
                self._socket, max_buffer_size=self.DEFAULT_BUFFER_SIZE)
        else:
            self._io_stream = IOStream(
                self._socket, max_buffer_size=self.DEFAULT_BUFFER_SIZE)

        self._io_stream.set_close_callback(self._stream_closed_callback)

    @tornado.gen.coroutine
    def _connect(self):
        if not self._io_stream:
            yield self._make_socket()
        if not self._connected:
            yield self._make_socket()
            _logger.debug('Connecting to {0}.'.format(self._address))
            try:
                yield tornado.gen.Task(self._io_stream.connect, self._address)
            except socket.error as error:
                raise NetworkError(error.args[0]) from error
            else:
                _logger.debug('Connected.')
                self._connected = True

    @tornado.gen.coroutine
    def fetch(self, request, recorder=None):
        _logger.debug('Request {0}.'.format(request))
        try:
            if recorder:
                with recorder.session() as recorder_session:
                    self._events.attach(recorder_session)
                    response = yield self._process_request(request)
            else:
                response = yield self._process_request(request)
        finally:
            self._events.clear()
            self.close()
        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _process_request(self, request):
        yield self._connect()

        self._events.request(request)

        try:
            yield self._send_request_header(request)
            yield self._send_request_body(request)

            response = yield self._read_response_header()
            # TODO: handle 100 Continue

            yield self._read_response_body(response)
        except socket.error as error:
            raise NetworkError(error.args[0]) from error

        self._events.response(response)

        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _send_request_header(self, request):
        _logger.debug('Sending headers.')
        for data in request.iter_header():
            self._events.request_data(data)
            yield tornado.gen.Task(self._io_stream.write, data)

    @tornado.gen.coroutine
    def _send_request_body(self, request):
        _logger.debug('Sending body.')
        for data in request.iter_body():
            self._events.request_data(data)
            yield tornado.gen.Task(self._io_stream.write, data)

    @tornado.gen.coroutine
    def _read_response_header(self):
        _logger.debug('Reading header.')
        response_header_data = yield tornado.gen.Task(
            self._io_stream.read_until_regex, br'\r?\n\r?\n')

        self._events.response_data(response_header_data)

        status_line, header = response_header_data.split(b'\n', 1)
        version, status_code, status_reason = Response.parse_status_line(
            status_line)
        response = Response(version, status_code, status_reason)
        response.fields.parse(header)

        raise tornado.gen.Return(response)

    @tornado.gen.coroutine
    def _read_response_body(self, response):
        _logger.debug('Reading body.')
        http_file = Body.new_temp_file()
        gzipped = 'gzip' in response.fields.get('Content-Encoding', '')
        chunked = False

        if re.search(r'chunked$|;',
        response.fields.get('Transfer-Encoding', '')):
            response.body = ResponseBody(http_file)
            chunked = True
            yield self._read_response_by_chunk(response)
        elif 'Content-Length' in response.fields:
            response.body = ResponseBody(http_file)
            yield self._read_response_by_length(response)
        else:
            response.body = ResponseBody(http_file)
            yield self._read_response_until_close(response)

        http_file.seek(0)
        response.body.transform(chunked=chunked, gzipped=gzipped)

    @tornado.gen.coroutine
    def _read_response_by_length(self, response):
        body_size = int(response.fields['Content-Length'])

        def response_callback(data):
            self._events.response_data(data)
            response.body.http_file.write(data)

        yield tornado.gen.Task(self._io_stream.read_bytes, body_size,
            streaming_callback=response_callback)

    @tornado.gen.coroutine
    def _read_response_by_chunk(self, response):
        while True:
            chunk_size = yield self._read_response_chunk(response)

            if chunk_size == 0:
                break

        yield self._read_response_chunked_trailer(response)

    @tornado.gen.coroutine
    def _read_response_chunk(self, response):
        _logger.debug('Reading chunk.')
        chunk_size_hex = yield tornado.gen.Task(
            self._io_stream.read_until_regex, b'[0-9A-Fa-f]+|.{13}')

        self._events.response_data(chunk_size_hex)
        response.body.http_file.write(chunk_size_hex)

        try:
            chunk_size = int(chunk_size_hex.strip(), 16)
        except ValueError as error:
            raise ProtocolError(error.args[0]) from error

        _logger.debug('Getting chunk size={0}.'.format(chunk_size))

        if not chunk_size:
            raise tornado.gen.Return(chunk_size)

        chunk_extension_data = yield tornado.gen.Task(
            self._io_stream.read_until, b'\n')

        self._events.response_data(chunk_extension_data)
        response.body.http_file.write(chunk_extension_data)

        def response_callback(data):
            self._events.response_data(data)
            response.body.http_file.write(data)

        yield tornado.gen.Task(self._io_stream.read_bytes, chunk_size,
            streaming_callback=response_callback)

        raise tornado.gen.Return(chunk_size)

    @tornado.gen.coroutine
    def _read_response_chunked_trailer(self, response):
        _logger.debug('Reading chunked trailer.')
        trailer_data = yield tornado.gen.Task(self._io_stream.read_until_regex,
            br'\r?\n\r?\n')

        self._events.response_data(trailer_data)
        response.fields.parse(trailer_data)

    @tornado.gen.coroutine
    def _read_response_until_close(self, response):
        def response_callback(data):
            self._events.response_data(data)
            response.body.http_file.write(data)

        yield tornado.gen.Task(self._io_stream.read_until_close,
            streaming_callback=response_callback)

    @property
    def ready(self):
        raise NotImplementedError()

    @property
    def connected(self):
        return self._connected

    def close(self):
        if self._io_stream:
            self._io_stream.close()

    def _stream_closed_callback(self):
        _logger.debug('Stream closed.')
        self._connected = False
        if self._io_stream.error:
            raise self._io_stream.error
        if self._io_stream.buffer_full:
            raise ProtocolError()


class HostConnectionPool(collections.Set):
    # TODO: remove old connection instances
    def __init__(self, host, port, request_queue, max_count=6,
    connection_factory=Connection):
        assert isinstance(host, str)
        assert isinstance(port, int) and port
        self._host = host
        self._port = port
        self._request_queue = request_queue
        self._connection_factory = connection_factory
        self._connections = set()
        self._connection_ready_queue = toro.Queue()
        self._max_count = max_count
        self._max_count_semaphore = toro.BoundedSemaphore(max_count)
        self._run()

    @tornado.gen.coroutine
    def _run(self):
        while True:
            _logger.debug('Host pool running ({0}:{1}).'.format(
                self._host, self._port))
            yield self._max_count_semaphore.acquire()
            self._process_request()

    @tornado.gen.coroutine
    def _process_request(self):
        request, kwargs, async_result = yield self._request_queue.get()

        _logger.debug('Host pool got request {0}'.format(request))

        connection = yield self._get_ready_connection()

        try:
            response = yield connection.fetch(request, **kwargs)
        except Exception as error:
            _logger.exception('Host pool got an error from fetch.')
            yield async_result.set(error)
        else:
            yield async_result.set(response)
        finally:
            _logger.debug('Host pool done {0}'.format(request))
            yield self._connection_ready_queue.put(connection)
            yield self._max_count_semaphore.release()

    @tornado.gen.coroutine
    def _get_ready_connection(self):
        try:
            _logger.debug('Getting a connection.')
            raise tornado.gen.Return(self._connection_ready_queue.get_nowait())
        except queue.Empty:
            if len(self._connections) < self._max_count:
                _logger.debug('Making another connection.')
                connection = self._connection_factory(self._host, self._port)
                self._connections.add(connection)
                raise tornado.gen.Return(connection)

        _logger.debug('Waiting for free connection.')
        raise tornado.gen.Return(self._connection_ready_queue.get())

    def __contains__(self, key):
        return key in self._connections

    def __iter__(self):
        return iter(self._connections)

    def __len__(self):
        return len(self._connections)


class ConnectionPool(collections.Mapping):
    Entry = collections.namedtuple('RequestQueueEntry', ['queue', 'pool'])

    def __init__(self, host_connection_pool_factory=HostConnectionPool):
        self._subqueues = {}
        self._host_connection_pool_factory = host_connection_pool_factory

    @tornado.gen.coroutine
    def put(self, request, kwargs, async_result):
        _logger.debug('Connection pool queue request {0}'.format(request))
        host = request.url_info.hostname
        port = request.url_info.port
        address = (host, port)

        if address not in self._subqueues:
            _logger.debug('New host pool.')
            self._subqueues[address] = self._subqueue_constructor(host, port)

        yield self._subqueues[address].queue.put(
            (request, kwargs, async_result))

    def _subqueue_constructor(self, host, port):
        subqueue = toro.Queue()
        return self.Entry(
            subqueue, self._host_connection_pool_factory(host, port, subqueue))

    def __getitem__(self, key):
        return self._subqueues[key]

    def __iter__(self):
        return iter(self._subqueues)

    def __len__(self):
        return len(self._subqueues)


class Client(object):
    def __init__(self, connection_pool=None):
        if connection_pool is not None:
            self._connection_pool = connection_pool
        else:
            self._connection_pool = ConnectionPool()

    @tornado.gen.coroutine
    def fetch(self, request, **kwargs):
        _logger.debug('Client fetch request {0}.'.format(request))
        async_result = toro.AsyncResult()
        yield self._connection_pool.put(request, kwargs, async_result)
        response = yield async_result.get()
        if isinstance(response, Exception):
            raise response
        else:
            raise tornado.gen.Return(response)


def decode_chunked_transfer(file):
    with wpull.util.reset_file_offset(file):
        out_file = tempfile.SpooledTemporaryFile(max_size=4194304)

        while True:
            line = file.readline()
            match = re.search(br'([0-9A-Za-z]+)', line)
            chunk_size = int(match.group(1), 16)

            if not chunk_size:
                break

            out_file.write(file.read(chunk_size))
            file.readline()  # discard deliminator before next size

        out_file.seek(0)
    return out_file
