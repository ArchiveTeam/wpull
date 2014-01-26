# encoding=utf-8
import abc
import base64
import contextlib
import gettext
import hashlib
import io
import logging
import os.path
import sys
from tempfile import NamedTemporaryFile
import tempfile
import time
import uuid

import wpull.backport.gzip
from wpull.namevalue import NameValueRecord
import wpull.util


_ = gettext.gettext


class BaseRecorder(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    @contextlib.contextmanager
    def session(self):
        pass

    def close(self):
        pass


class BaseRecorderSession(object, metaclass=abc.ABCMeta):
    def pre_request(self, request):
        pass

    def request(self, request):
        pass

    def request_data(self, data):
        pass

    def pre_response(self, response):
        pass

    def response(self, response):
        pass

    def response_data(self, data):
        pass


class DemuxRecorder(BaseRecorder):
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders

    @contextlib.contextmanager
    def session(self):
        dmux = DemuxRecorderSession(self._recorders)
        with dmux:
            yield dmux

    def close(self):
        for recorder in self._recorders:
            recorder.close()


class DemuxRecorderSession(BaseRecorderSession):
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders
        self._sessions = None
        self._contexts = None

    def __enter__(self):
        self._contexts = [recorder.session() for recorder in self._recorders]
        self._sessions = [context.__enter__() for context in self._contexts]

    def pre_request(self, request):
        for session in self._sessions:
            session.pre_request(request)

    def request(self, request):
        for session in self._sessions:
            session.request(request)

    def request_data(self, data):
        for session in self._sessions:
            session.request_data(data)

    def pre_response(self, response):
        for session in self._sessions:
            session.pre_response(response)

    def response(self, response):
        for session in self._sessions:
            session.response(response)

    def response_data(self, data):
        for session in self._sessions:
            session.response_data(data)

    def __exit__(self, *args):
        for context in self._contexts:
            context.__exit__(*args)


class WARCRecord(object):
    VERSION = 'WARC/1.0'
    WARC_TYPE = 'WARC-Type'
    CONTENT_TYPE = 'Content-Type'
    WARC_DATE = 'WARC-Date'
    WARC_RECORD_ID = 'WARC-Record-ID'
    WARCINFO = 'warcinfo'
    WARC_FIELDS = 'application/warc-fields'
    REQUEST = 'request'
    RESPONSE = 'response'
    TYPE_REQUEST = 'application/http;msgtype=request'
    TYPE_RESPONSE = 'application/http;msgtype=response'

    def __init__(self):
        self.fields = NameValueRecord()
        self.block_file = None

    def set_common_fields(self, warc_type, content_type):
        self.fields[self.WARC_TYPE] = warc_type
        self.fields[self.CONTENT_TYPE] = content_type
        self.fields[self.WARC_DATE] = wpull.util.datetime_str()
        self.fields[self.WARC_RECORD_ID] = '<{0}>'.format(uuid.uuid4().urn)

    def compute_checksum(self, payload_offset=None):
        if not self.block_file:
            self.fields['Content-Length'] = '0'
            return

        block_hasher = hashlib.sha1()
        payload_hasher = hashlib.sha1()

        with wpull.util.reset_file_offset(self.block_file):
            if payload_offset is not None:
                data = self.block_file.read(payload_offset)
                block_hasher.update(data)

            while True:
                data = self.block_file.read(4096)
                if data == b'':
                    break
                block_hasher.update(data)
                payload_hasher.update(data)

            content_length = self.block_file.tell()

        content_hash = block_hasher.digest()

        self.fields['WARC-Block-Digest'] = 'sha1:{0}'.format(
            base64.b32encode(content_hash).decode()
        )

        if payload_offset is not None:
            payload_hash = payload_hasher.digest()
            self.fields['WARC-Payload-Digest'] = 'sha1:{0}'.format(
                base64.b32encode(payload_hash).decode()
            )

        self.fields['Content-Length'] = str(content_length)

    def __iter__(self):
        yield self.VERSION.encode()
        yield b'\r\n'
        yield bytes(self.fields)
        yield b'\r\n'

        with wpull.util.reset_file_offset(self.block_file):
            while True:
                data = self.block_file.read(4096)
                if data == b'':
                    break
                yield data

        yield b'\r\n\r\n'

    def __str__(self):
        return ''.join(iter(self))


class WARCRecorder(BaseRecorder):
    def __init__(self, filename, compress=True, extra_fields=None,
    temp_dir=None, log=True, appending=False):
        self._filename = filename
        self._gzip_enabled = compress
        self._temp_dir = temp_dir
        self._warcinfo_record = WARCRecord()
        self._log_record = None
        self._log_handler = None

        if not appending:
            self._truncate_existing_file()

        self._populate_warcinfo(extra_fields)

        if log:
            self._log_record = WARCRecord()
            self._setup_log()

        self.write_record(self._warcinfo_record)

    def _truncate_existing_file(self):
        if os.path.exists(self._filename):
            with open(self._filename, 'wb'):
                pass

    def _populate_warcinfo(self, extra_fields=None):
        self._warcinfo_record.set_common_fields(
            WARCRecord.WARCINFO, WARCRecord.WARC_FIELDS)

        info_fields = NameValueRecord()
        info_fields['Software'] = 'Wpull/{0} Python/{1}'.format(
            wpull.version.__version__, wpull.util.python_version())
        info_fields['format'] = 'WARC File Format 1.0'
        info_fields['conformsTo'] = \
            'http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf'

        if extra_fields:
            for name, value in extra_fields:
                info_fields.add(name, value)

        self._warcinfo_record.block_file = io.BytesIO(
            bytes(info_fields) + b'\r\n')
        self._warcinfo_record.compute_checksum()

    def _setup_log(self):
        logger = logging.getLogger()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._log_record.block_file = NamedTemporaryFile(
            prefix='wpull-warc-',
            dir=self._temp_dir,
            suffix='.log',
        )
        self._log_handler = handler = logging.FileHandler(
            self._log_record.block_file.name, encoding='utf-8')

        handler.setFormatter(formatter)
        logger.addHandler(handler)
        handler.setLevel(logging.INFO)

    @contextlib.contextmanager
    def session(self):
        recorder_session = WARCRecorderSession(self, self._temp_dir)
        yield recorder_session

    def write_record(self, record):
        # FIXME: probably not a good idea to modifiy arguments passed to us
        # TODO: add extra gzip headers that wget uses
        record.fields['WARC-Warcinfo-ID'] = self._warcinfo_record.fields[
            WARCRecord.WARC_RECORD_ID]

        if self._gzip_enabled:
            open_func = wpull.backport.gzip.GzipFile
        else:
            open_func = open

        with open_func(self._filename, mode='ab') as out_file:
            for data in record:
                out_file.write(data)

    def close(self):
        if self._log_record:
            self._log_handler.flush()
            self._log_handler.close()

            logger = logging.getLogger()
            logger.removeHandler(self._log_handler)
            self._log_handler = None

            self._log_record.block_file.seek(0)
            self._log_record.set_common_fields('resource', 'text/plain')

            self._log_record.fields['WARC-Target-URI'] = \
                'urn:X-wpull:log'

            self._log_record.compute_checksum()
            self.write_record(self._log_record)

            self._log_record.block_file.close()


class WARCRecorderSession(BaseRecorderSession):
    def __init__(self, recorder, temp_dir=None):
        self._recorder = recorder
        self._request = None
        self._request_record = None
        self._response_record = None
        self._temp_dir = temp_dir
        self._response_temp_file = self._new_temp_file()

    def _new_temp_file(self):
        return tempfile.SpooledTemporaryFile(
            max_size=1048576,
            dir=self._temp_dir
        )

    def pre_request(self, request):
        self._request = request
        self._request_record = record = WARCRecord()
        record.set_common_fields(WARCRecord.REQUEST, WARCRecord.TYPE_REQUEST)
        record.fields['WARC-Target-URI'] = request.url_info.url
        record.fields['WARC-IP-Address'] = request.address[0]
        record.block_file = self._new_temp_file()

    def request_data(self, data):
        self._request_record.block_file.write(data)

    def request(self, request):
        payload_offset = len(request.header())

        self._request_record.block_file.seek(0)
        self._request_record.compute_checksum(payload_offset=payload_offset)
        self._recorder.write_record(self._request_record)

    def pre_response(self, response):
        self._response_record = record = WARCRecord()
        record.set_common_fields(WARCRecord.RESPONSE, WARCRecord.TYPE_RESPONSE)
        record.fields['WARC-Target-URI'] = self._request.url_info.url
        record.fields['WARC-IP-Address'] = self._request.address[0]
        record.fields['WARC-Concurrent-To'] = self._request_record.fields[
            WARCRecord.WARC_RECORD_ID]
        record.block_file = self._response_temp_file

    def response_data(self, data):
        self._response_temp_file.write(data)

    def response(self, response):
        payload_offset = len(response.header())

        self._response_record.block_file.seek(0)
        self._response_record.compute_checksum(payload_offset=payload_offset)
        self._recorder.write_record(self._response_record)


class DebugPrintRecorder(BaseRecorder):
    @contextlib.contextmanager
    def session(self):
        print('Session started')
        try:
            yield DebugPrintRecorderSession()
        finally:
            print('Session ended')


class DebugPrintRecorderSession(BaseRecorderSession):
    def pre_request(self, request):
        print(request)

    def request(self, request):
        print(request)

    def request_data(self, data):
        print(data)

    def pre_response(self, response):
        print(response)

    def response(self, response):
        print(response)

    def response_data(self, data):
        print(data)


class PrintServerResponseRecorder(BaseRecorder):
    @contextlib.contextmanager
    def session(self):
        yield PrintServerResponseRecorderSession()


class PrintServerResponseRecorderSession(BaseRecorderSession):
    def response(self, response):
        print(response.header().decode())


class ProgressRecorder(BaseRecorder):
    def __init__(self, bar_style=False, stream=sys.stderr):
        self._bar_style = bar_style
        self._stream = stream

    @contextlib.contextmanager
    def session(self):
        yield ProgressRecorderSession(self._bar_style, self._stream)


class ProgressRecorderSession(BaseRecorderSession):
    def __init__(self, bar_style, stream=sys.stderr):
        self._content_length = None
        self._bytes_received = 0
        self._response = None
        self._last_flush_time = 0
        self._bar_style = bar_style
        self._stream = stream

    def pre_request(self, request):
        print(
            _('Requesting {url}... ').format(url=request.url_info.url),
            end='',
            file=self._stream,
        )
        self._stream.flush()

    def pre_response(self, response):
        print(
            response.status_code, response.status_reason, file=self._stream
        )

        content_length = response.fields.get('Content-Length')

        if content_length:
            self._content_length = int(content_length)

        print(
            _('Length: {content_length} [{content_type}]').format(
                content_length=self._content_length,
                content_type=response.fields.get('Content-Type')
            ),
            file=self._stream,
        )

        self._response = response

    def response_data(self, data):
        if not self._response:
            return

        self._bytes_received += len(data)

        if self._bar_style and self._content_length:
            self._print_bar()
        else:
            self._print_dots()

    def _print_bar(self):
        # TODO: print a bar
        pass

    def _print_dots(self):
        time_now = time.time()

        if time_now - self._last_flush_time > 2.0:
            print('.', end='', file=self._stream)
            self._stream.flush()
            self._last_flush_time = time.time()

    def response(self, response):
        print(file=self._stream)
        print(
            _('Bytes received: {bytes_received}').format(
                bytes_received=self._bytes_received),
            file=self._stream
        )
