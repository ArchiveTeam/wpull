# encoding=utf-8
'''HTTP communication recorders.'''
import abc
import base64
import contextlib
import datetime
import gettext
import hashlib
import http.client
import io
import itertools
import logging
import os.path
import re
import sys
from tempfile import NamedTemporaryFile
import tempfile
import time
import uuid

import wpull.backport.gzip
from wpull.namevalue import NameValueRecord
from wpull.network import BandwidthMeter
import wpull.util


_ = gettext.gettext


class BaseRecorder(object, metaclass=abc.ABCMeta):
    '''Base class for recorders.'''
    @abc.abstractmethod
    @contextlib.contextmanager
    def session(self):
        '''Return a new session.'''
        pass

    def close(self):
        '''Perform any clean up actions.'''
        pass


class BaseRecorderSession(object, metaclass=abc.ABCMeta):
    def pre_request(self, request):
        '''Callback for when a request is about to be made.'''
        pass

    def request(self, request):
        '''Callback for when a request has been made.'''
        pass

    def request_data(self, data):
        '''Callback for the bytes that was sent.'''
        pass

    def pre_response(self, response):
        '''Callback for when the response header has been received.'''
        pass

    def response(self, response):
        '''Callback for when the response has been completely received.'''
        pass

    def response_data(self, data):
        '''Callback for the bytes that was received.'''
        pass


class DemuxRecorder(BaseRecorder):
    '''Put multiple recorders into one.'''
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
    '''A record in a WARC file.'''
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
        '''Set the required fields for the record.'''
        self.fields[self.WARC_TYPE] = warc_type
        self.fields[self.CONTENT_TYPE] = content_type
        self.fields[self.WARC_DATE] = wpull.util.datetime_str()
        self.fields[self.WARC_RECORD_ID] = '<{0}>'.format(uuid.uuid4().urn)

    def compute_checksum(self, payload_offset=None):
        '''Compute and add the checksum data to the record fields.'''
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
    '''Record to WARC file.

    For the WARC file specification, see
    http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf.

    Args:
        filename: The filename (excluding the extension)
        compress: If True, files will be compressed with gzip
        extra_fields: A list of key-value pairs containing extra metadata
            fields
        temp_dir: Directory to use for temporary files
        log: Include the program logging messages in the WARC file
        appending: If True, the file is not overwritten upon opening
    '''
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
        '''Add the metadata to the Warcinfo record.'''
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
        '''Set up the logging file.'''
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
        '''Append the record to the WARC file.'''
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
        '''Close the WARC file and clean up any logging handlers.'''
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
    '''Print the server HTTP response.'''
    @contextlib.contextmanager
    def session(self):
        yield PrintServerResponseRecorderSession()


class PrintServerResponseRecorderSession(BaseRecorderSession):
    def response(self, response):
        print(response.header().decode())


class ProgressRecorder(BaseRecorder):
    '''Print file download progress.'''
    def __init__(self, bar_style=False, stream=sys.stderr):
        self._bar_style = bar_style
        self._stream = stream

    @contextlib.contextmanager
    def session(self):
        if self._bar_style:
            yield BarProgressRecorderSession(stream=self._stream)
        else:
            yield DotProgressRecorderSession(stream=self._stream)


class BaseProgressRecorderSession(BaseRecorderSession):
    def __init__(self, stream=sys.stderr):
        self._stream = stream
        self._bytes_received = 0
        self._content_length = None
        self._response = None

    def _print(self, *args):
        string = ' '.join([str(arg) for arg in args])
        print(string, end='', file=self._stream)

    def _println(self, *args):
        string = ' '.join([str(arg) for arg in args])
        print(string, file=self._stream)

    def _flush(self):
        self._stream.flush()

    def pre_request(self, request):
        self._print(
            _('Requesting {url}... ').format(url=request.url_info.url),
        )
        self._flush()

    def pre_response(self, response):
        self._println(response.status_code, response.status_reason)

        content_length = response.fields.get('Content-Length')

        if content_length:
            try:
                self._content_length = int(content_length)
            except ValueError:
                self._content_length = None

        self._println(
            _('Length: {content_length} [{content_type}]').format(
                content_length=self._content_length,
                content_type=response.fields.get('Content-Type')
            ),
        )

        self._response = response

    def response_data(self, data):
        if not self._response:
            return

        self._bytes_received += len(data)

    def response(self, response):
        self._println()
        self._println(
            _('Bytes received: {bytes_received}').format(
                bytes_received=self._bytes_received)
        )


class DotProgressRecorderSession(BaseProgressRecorderSession):
    def __init__(self, dot_interval=2.0, **kwargs):
        super().__init__(**kwargs)
        self._last_flush_time = 0
        self._dot_interval = dot_interval

    def response_data(self, data):
        super().response_data(data)

        if not self._response:
            return

        time_now = time.time()

        if time_now - self._last_flush_time > self._dot_interval:
            self._print_dots()
            self._flush()

            self._last_flush_time = time_now

    def _print_dots(self):
        self._print('.')


class BarProgressRecorderSession(BaseProgressRecorderSession):
    def __init__(self, update_interval=0.5, bar_width=25, **kwargs):
        super().__init__(**kwargs)
        self._last_flush_time = 0
        self._update_interval = update_interval
        self._bytes_continued = 0
        self._total_size = None
        self._bar_width = bar_width
        self._throbber_index = 0
        self._throbber_iter = itertools.cycle(
            itertools.chain(
                range(bar_width), reversed(range(1, bar_width - 1))
        ))
        self._bandwidth_meter = BandwidthMeter()
        self._start_time = time.time()

    def pre_response(self, response):
        super().pre_response(response)

        if response.status_code == http.client.PARTIAL_CONTENT:
            match = re.search(
                r'bytes +([0-9]+)-([0-9]+)/([0-9]+)',
                 response.fields.get('Content-Range', '')
             )

            if match:
                self._bytes_continued = int(match.group(1))
                self._total_size = int(match.group(3))
        else:
            self._total_size = self._content_length

    def response_data(self, data):
        super().response_data(data)

        if not self._response:
            return

        self._bandwidth_meter.feed(len(data))

        time_now = time.time()

        if time_now - self._last_flush_time > self._update_interval:
            self._print_status()
            self._stream.flush()

            self._last_flush_time = time_now

    def _print_status(self):
        self._clear_line()

        if self._total_size:
            self._print_percent()
            self._print(' ')
            self._print_bar()
        else:
            self._print_throbber()

        self._print(' ')
        self._print_size_downloaded()
        self._print(' ')
        self._print_duration()
        self._print(' ')
        self._print_speed()
        self._flush()

    def _clear_line(self):
        self._print('\x1b[1G')
        self._print('\x1b[2K')

    def _print_throbber(self):
        self._print('[')

        for position in range(self._bar_width):
            self._print('O' if position == self._throbber_index else ' ')

        self._print(']')

        self._throbber_index = next(self._throbber_iter)

    def _print_bar(self):
        self._print('[')

        for position in range(self._bar_width):
            position_fraction = position / (self._bar_width - 1)
            position_bytes = position_fraction * self._total_size

            if position_bytes < self._bytes_continued:
                self._print('+')
            elif position_bytes <= \
            self._bytes_continued + self._bytes_received:
                self._print('=')
            else:
                self._print(' ')

        self._print(']')

    def _print_size_downloaded(self):
        self._print(wpull.util.format_size(self._bytes_received))

    def _print_duration(self):
        duration = int(time.time() - self._start_time)
        self._print(datetime.timedelta(seconds=duration))

    def _print_speed(self):
        speed = self._bandwidth_meter.speed()
        speed_str = _('{preformatted_file_size}/s').format(
            preformatted_file_size=wpull.util.format_size(speed)
        )
        self._print(speed_str)

    def _print_percent(self):
        fraction_done = ((self._bytes_continued + self._bytes_received) /
            self._total_size)

        self._print('{fraction_done:.1%}'.format(fraction_done=fraction_done))
