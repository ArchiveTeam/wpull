# encoding=utf-8
'''HTTP communication recorders.'''
import abc
import contextlib
import datetime
import gettext
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

import namedlist

import wpull.backport.gzip
from wpull.namevalue import NameValueRecord
from wpull.network import BandwidthMeter
import wpull.util
import wpull.version
from wpull.warc import WARCRecord


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BaseRecorder(object, metaclass=abc.ABCMeta):
    '''Base class for recorders.

    Recorders are designed to be passed to a :class:`.http.client.Client`.
    '''
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
    '''Demux recorder session.'''
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


WARCRecorderParams = namedlist.namedtuple(
    'WARCRecorderParamsType',
    [
        ('compress', True),
        ('extra_fields', None),
        ('temp_dir', None),
        ('log', True),
        ('appending', False),
        ('digests', True),
        ('cdx', None),
        ('max_size', None),
        ('url_table', None),
        ('software_string', None)
    ]
)
''':class:`WARCRecorder` parameters.

Args:
    compress (bool): If True, files will be compressed with gzip
    extra_fields (list): A list of key-value pairs containing extra
        metadata fields
    temp_dir (str): Directory to use for temporary files
    log (bool): Include the program logging messages in the WARC file
    appending (bool): If True, the file is not overwritten upon opening
    digests (bool): If True, the SHA1 hash digests will be written.
    cdx (bool): If True, a CDX file will be written.
    max_size (int): If provided, output files are named like
        ``name-00000.ext`` and the log file will be in ``name-meta.ext``.
    url_table (:class:`.database.URLTable`): If given, then ``revist``
        records will be written.
    software_string (str): The value for the ``software`` field in the
        Warcinfo record.
'''


class WARCRecorder(BaseRecorder):
    '''Record to WARC file.

    Args:
        filename (str): The filename (without the extension).
        params (:class:`WARCRecorderParams`): Parameters.
    '''
    CDX_DELIMINATOR = ' '
    '''Default CDX delimiter.'''
    DEFAULT_SOFTWARE_STRING = 'Wpull/{0} Python/{1}'.format(
        wpull.version.__version__, wpull.util.python_version()
    )
    '''Default software string.'''

    def __init__(self, filename, params=None):
        self._prefix_filename = filename
        self._params = params or WARCRecorderParams()
        self._warcinfo_record = None
        self._sequence_num = 0
        self._log_record = None
        self._log_handler = None
        self._warc_filename = None
        self._cdx_filename = None

        if params.log:
            self._log_record = WARCRecord()
            self._setup_log()

        self._start_new_warc_file()

        if self._params.cdx:
            self._start_new_cdx_file()

    def _start_new_warc_file(self, meta=False):
        if self._params.max_size is None:
            sequence_name = ''
        elif meta:
            sequence_name = '-meta'
        else:
            sequence_name = '-{0:05d}'.format(self._sequence_num)

        if self._params.compress:
            extension = 'warc.gz'
        else:
            extension = 'warc'

        self._warc_filename = '{0}{1}.{2}'.format(
            self._prefix_filename, sequence_name, extension
        )

        _logger.debug('WARC file at {0}'.format(self._warc_filename))

        if not self._params.appending:
            wpull.util.truncate_file(self._warc_filename)

        self._warcinfo_record = WARCRecord()
        self._populate_warcinfo(self._params.extra_fields)
        self.write_record(self._warcinfo_record)

    def _start_new_cdx_file(self):
        self._cdx_filename = '{0}.cdx'.format(self._prefix_filename)

        if not self._params.appending:
            wpull.util.truncate_file(self._cdx_filename)
            self._write_cdx_header()
        elif not os.path.exists(self._cdx_filename):
            self._write_cdx_header()

    def _populate_warcinfo(self, extra_fields=None):
        '''Add the metadata to the Warcinfo record.'''
        self._warcinfo_record.set_common_fields(
            WARCRecord.WARCINFO, WARCRecord.WARC_FIELDS)

        info_fields = NameValueRecord()
        info_fields['Software'] = self._params.software_string \
            or self.DEFAULT_SOFTWARE_STRING
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
            dir=self._params.temp_dir,
            suffix='.log',
        )
        self._log_handler = handler = logging.FileHandler(
            self._log_record.block_file.name, encoding='utf-8')

        logger.setLevel(logging.DEBUG)
        logger.debug('Wpull needs the root logger level set to DEBUG.')

        handler.setFormatter(formatter)
        logger.addHandler(handler)
        handler.setLevel(logging.INFO)

    @contextlib.contextmanager
    def session(self):
        recorder_session = WARCRecorderSession(
            self,
            temp_dir=self._params.temp_dir, url_table=self._params.url_table
        )
        yield recorder_session

        if self._params.max_size is not None \
        and os.path.getsize(self._warc_filename) > self._params.max_size:
            self._sequence_num += 1

            _logger.debug('Starting new warc file due to max size.')
            self._start_new_warc_file()

    def set_length_and_maybe_checksums(self, record, payload_offset=None):
        '''Set the content length and possibly the checksums.'''
        if self._params.digests:
            record.compute_checksum(payload_offset)
        else:
            record.set_content_length()

    def write_record(self, record):
        '''Append the record to the WARC file.'''
        # FIXME: probably not a good idea to modifiy arguments passed to us
        # TODO: add extra gzip headers that wget uses
        record.fields['WARC-Warcinfo-ID'] = self._warcinfo_record.fields[
            WARCRecord.WARC_RECORD_ID]

        _logger.debug('Writing WARC record {0}.'.format(
            record.fields['WARC-Type']))

        if self._params.compress:
            open_func = wpull.backport.gzip.GzipFile
        else:
            open_func = open

        if os.path.exists(self._warc_filename):
            before_offset = os.path.getsize(self._warc_filename)
        else:
            before_offset = 0

        try:
            with open_func(self._warc_filename, mode='ab') as out_file:
                for data in record:
                    out_file.write(data)
        except (OSError, IOError) as error:
            _logger.info(
                _('Rolling back file {filename} to length {length}.')\
                .format(filename=self._warc_filename, length=before_offset)
            )
            with open(self._warc_filename, mode='wb') as out_file:
                out_file.truncate(before_offset)
            raise error

        after_offset = os.path.getsize(self._warc_filename)

        if self._cdx_filename:
            raw_file_offset = before_offset
            raw_file_record_size = after_offset - before_offset

            self._write_cdx_field(
                record, raw_file_record_size, raw_file_offset
            )

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

            if self._params.max_size is not None:
                self._start_new_warc_file(meta=True)

            self.set_length_and_maybe_checksums(self._log_record)
            self.write_record(self._log_record)

            self._log_record.block_file.close()

    def _write_cdx_header(self):
        '''Write the CDX header.

        It writes the fields:

        1. a: original URL
        2. b: UNIX timestamp
        3. m: MIME Type from the HTTP Content-type
        4. s: response code
        5. k: new style checksum
        6. S: raw file record size
        7. V: offset in raw file
        8. g: filename of raw file
        9. u: record ID
        '''
        with open(self._cdx_filename, mode='a', encoding='utf-8') as out_file:
            out_file.write(self.CDX_DELIMINATOR)
            out_file.write(self.CDX_DELIMINATOR.join((
                'CDX',
                'a', 'b', 'm', 's',
                'k', 'S', 'V', 'g',
                'u'
            )))
            out_file.write('\n')

    def _write_cdx_field(self, record, raw_file_record_size, raw_file_offset):
        '''Write the CDX field if needed.'''
        if record.fields[WARCRecord.WARC_TYPE] != WARCRecord.RESPONSE \
        or not re.match(r'application/http; *msgtype *= *response',
        record.fields[WARCRecord.CONTENT_TYPE]):
            return

        url = record.fields['WARC-Target-URI']

        _logger.debug('Writing CDX record {0}.'.format(url))

        http_header = record.get_http_header()

        if http_header:
            mime_type = self.parse_mimetype(
                http_header.fields.get('Content-Type', '')
            ) or '-'
            response_code = str(http_header.status_code)
        else:
            mime_type = '-'
            response_code = '-'

        timestamp = str(int(
            wpull.util.parse_iso8601_str(record.fields[WARCRecord.WARC_DATE])
        ))

        checksum = record.fields.get('WARC-Payload-Digest', '')

        if checksum.startswith('sha1:'):
            checksum = checksum.replace('sha1:', '', 1)
        else:
            checksum = '-'

        raw_file_record_size_str = str(raw_file_record_size)
        raw_file_offset_str = str(raw_file_offset)
        filename = os.path.basename(self._warc_filename)
        record_id = record.fields[WARCRecord.WARC_RECORD_ID]
        fields_strs = (
            url,
            timestamp,
            mime_type,
            response_code,
            checksum,
            raw_file_record_size_str,
            raw_file_offset_str,
            filename,
            record_id
        )

        with open(self._cdx_filename, mode='a', encoding='utf-8') as out_file:
            out_file.write(self.CDX_DELIMINATOR.join(fields_strs))
            out_file.write('\n')

    @classmethod
    def parse_mimetype(cls, value):
        '''Return the MIME type from a Content-Type string.

        Returns:
            str, None: A string in the form ``type/subtype`` or None.
        '''
        match = re.match(r'([a-zA-Z0-9-]+/[a-zA-Z0-9-]+)', value)

        if match:
            return match.group(1)


class WARCRecorderSession(BaseRecorderSession):
    '''WARC Recorder Session.'''
    def __init__(self, recorder, temp_dir=None, url_table=None):
        self._recorder = recorder
        self._temp_dir = temp_dir
        self._url_table = url_table
        self._request = None
        self._request_record = None
        self._response_record = None
        self._response_temp_file = self._new_temp_file()

    def _new_temp_file(self):
        '''Return new temp file.'''
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
        self._recorder.set_length_and_maybe_checksums(
            self._request_record, payload_offset=payload_offset
        )
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
        self._recorder.set_length_and_maybe_checksums(
            self._response_record,
            payload_offset=payload_offset
        )

        if self._url_table is not None:
            self._record_revisit(payload_offset)

        self._recorder.write_record(self._response_record)

    def _record_revisit(self, payload_offset):
        '''Record the revisit if possible.'''
        fields = self._response_record.fields

        ref_record_id = self._url_table.get_revisit_id(
            fields['WARC-Target-URI'],
            fields.get('WARC-Payload-Digest', '').upper().replace('SHA1:', '')
        )

        if ref_record_id:
            try:
                self._response_record.block_file.truncate(payload_offset)
            except TypeError:
                self._response_record.block_file.seek(0)

                data = self._response_record.block_file.read(payload_offset)

                self._response_record.block_file.truncate()
                self._response_record.block_file.seek(0)
                self._response_record.block_file.write(data)

            self._recorder.set_length_and_maybe_checksums(
                self._response_record
            )

            fields[WARCRecord.WARC_TYPE] = WARCRecord.REVISIT
            fields['WARC-Refers-To'] = ref_record_id
            fields['WARC-Profile'] = WARCRecord.SAME_PAYLOAD_DIGEST_URI
            fields['WARC-Truncated'] = 'length'


class DebugPrintRecorder(BaseRecorder):
    '''Debugging print recorder.'''
    @contextlib.contextmanager
    def session(self):
        print('Session started')
        try:
            yield DebugPrintRecorderSession()
        finally:
            print('Session ended')


class DebugPrintRecorderSession(BaseRecorderSession):
    '''Debugging print recorder session.'''
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
    '''Print Server Response Recorder Session.'''
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
    '''Base Progress Recorder Session.'''
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
    '''Dot Progress Recorder Session.

    This session is responsible for printing dots every few seconds
    when it receives data.
    '''
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
    '''Bar Progress Recorder Session.

    This session is responsible for displaying the ASCII bar
    and stats.
    '''
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

    def response(self, response):
        self._print_status()
        self._stream.flush()
        super().response(response)

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
        self._print(wpull.string.format_size(self._bytes_received))

    def _print_duration(self):
        duration = int(time.time() - self._start_time)
        self._print(datetime.timedelta(seconds=duration))

    def _print_speed(self):
        if self._bandwidth_meter.num_samples:
            speed = self._bandwidth_meter.speed()
            speed_str = _('{preformatted_file_size}/s').format(
                preformatted_file_size=wpull.string.format_size(speed)
            )
        else:
            speed_str = _('-- B/s')

        self._print(speed_str)

    def _print_percent(self):
        fraction_done = ((self._bytes_continued + self._bytes_received) /
            self._total_size)

        self._print('{fraction_done:.1%}'.format(fraction_done=fraction_done))


class OutputDocumentRecorder(BaseRecorder):
    '''Output documents as a stream.'''
    def __init__(self, file, with_headers=False):
        self._file = file
        self._with_headers = with_headers

    @contextlib.contextmanager
    def session(self):
        yield OutputDocumentRecorderSession(self._file, self._with_headers)

    def close(self):
        self._file.close()


class OutputDocumentRecorderSession(BaseRecorderSession):
    '''Output document recorder session.'''
    def __init__(self, file, with_headers=False):
        self._file = file
        self._with_headers = with_headers
        self._response = None

    def pre_response(self, response):
        self._response = response

    def response_data(self, data):
        if self._with_headers and not self._response:
            self._file.write(data)

        if self._response:
            self._response.body.content_file.seek(-len(data), 1)
            self._file.write(self._response.body.content_file.read(len(data)))
