from tempfile import NamedTemporaryFile
import contextlib
import gettext
import gzip
import io
import logging
import os.path
import re
import shutil

import namedlist

from wpull.backport.logging import BraceMessage as __
from wpull.namevalue import NameValueRecord
from wpull.recorder.base import BaseRecorder, BaseRecorderSession
from wpull.warc import WARCRecord
import wpull.version


try:
    from textwrap import indent as textwrap_indent
except ImportError:
    from wpull.backport.textwrap import indent as textwrap_indent


_logger = logging.getLogger(__name__)
_ = gettext.gettext


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
        ('move_to', None),
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
    move_to (str): If provided, completed WARC files and CDX files will be
        moved to the given directory
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

        _logger.debug(__('WARC file at {0}', self._warc_filename))

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
        self._log_handler = handler = logging.StreamHandler(
            io.TextIOWrapper(self._log_record.block_file, encoding='utf-8'))

        logger.setLevel(logging.DEBUG)
        logger.debug('Wpull needs the root logger level set to DEBUG.')

        handler.setFormatter(formatter)
        logger.addHandler(handler)
        handler.setLevel(logging.INFO)

    @contextlib.contextmanager
    def session(self):
        recorder_session = WARCRecorderSessionDelegate(
            self,
            temp_dir=self._params.temp_dir, url_table=self._params.url_table
        )
        try:
            yield recorder_session
        finally:
            recorder_session.close()

        if self._params.max_size is not None \
           and os.path.getsize(self._warc_filename) > self._params.max_size:
            self._sequence_num += 1

            if self._params.move_to is not None:
                self._move_file_to_dest_dir(self._warc_filename)

            _logger.debug('Starting new warc file due to max size.')
            self._start_new_warc_file()

    def _move_file_to_dest_dir(self, filename):
        '''Move the file to the ``move_to`` directory.'''
        assert self._params.move_to

        if os.path.isdir(self._params.move_to):
            _logger.debug('Moved %s to %s.', self._warc_filename,
                          self._params.move_to)
            shutil.move(filename, self._params.move_to)
        else:
            _logger.error('%s is not a directory; not moving %s.',
                          self._params.move_to, filename)

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

        _logger.debug(__('Writing WARC record {0}.',
                         record.fields['WARC-Type']))

        if self._params.compress:
            open_func = gzip.GzipFile
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
            _logger.info(__(
                _('Rolling back file {filename} to length {length}.'),
                filename=self._warc_filename, length=before_offset
            ))
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

            logger = logging.getLogger()
            logger.removeHandler(self._log_handler)

            self._log_record.block_file.seek(0)
            self._log_record.set_common_fields('resource', 'text/plain')

            self._log_record.fields['WARC-Target-URI'] = \
                'urn:X-wpull:log'

            if self._params.max_size is not None:
                if self._params.move_to is not None:
                    self._move_file_to_dest_dir(self._warc_filename)

                self._start_new_warc_file(meta=True)

            self.set_length_and_maybe_checksums(self._log_record)
            self.write_record(self._log_record)

            self._log_record.block_file.close()
            self._log_handler.close()
            self._log_handler = None

            if self._params.move_to is not None:
                self._move_file_to_dest_dir(self._warc_filename)

        if self._cdx_filename and self._params.move_to is not None:
            self._move_file_to_dest_dir(self._cdx_filename)

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

        _logger.debug(__('Writing CDX record {0}.', url))

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


class BaseWARCRecorderSession(BaseRecorderSession):
    '''Base WARC recorder session.'''
    def __init__(self, recorder, temp_dir=None, url_table=None):
        self._recorder = recorder
        self._temp_dir = temp_dir
        self._url_table = url_table

    def _new_temp_file(self, hint='warcrecsess'):
        '''Return new temp file.'''
        return wpull.body.new_temp_file(
            directory=self._temp_dir, hint=hint
        )


class WARCRecorderSessionDelegate(BaseWARCRecorderSession):
    '''Delegate to either HTTP or FTP recorder session.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._child_session = None

    def close(self):
        if self._child_session:
            return self._child_session.close()

    def pre_request(self, request):
        if not self._child_session:
            self._child_session = HTTPWARCRecorderSession(
                self._recorder, temp_dir=self._temp_dir,
                url_table=self._url_table
            )

        self._child_session.pre_request(request)

    def request(self, request):
        self._child_session.request(request)

    def request_data(self, data):
        self._child_session.request_data(data)

    def pre_response(self, response):
        self._child_session.pre_response(response)

    def response(self, response):
        self._child_session.response(response)

    def response_data(self, data):
        self._child_session.response_data(data)

    def begin_control(self, request):
        if not self._child_session:
            self._child_session = FTPWARCRecorderSession(
                self._recorder, temp_dir=self._temp_dir,
                url_table=self._url_table
            )

        self._child_session.begin_control(request)

    def request_control_data(self, data):
        self._child_session.request_control_data(data)

    def response_control_data(self, data):
        self._child_session.response_control_data(data)

    def end_control(self, response):
        self._child_session.end_control(response)


class HTTPWARCRecorderSession(BaseWARCRecorderSession):
    '''HTTP WARC Recorder Session.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request = None
        self._request_record = None
        self._response_record = None
        self._response_temp_file = self._new_temp_file(hint='warcsesrsp')

    def close(self):
        if self._response_temp_file:
            self._response_temp_file.close()

        if self._request_record and self._request_record.block_file:
            self._request_record.block_file.close()

        if self._response_record and self._response_record.block_file:
            self._response_record.block_file.close()

    def pre_request(self, request):
        self._request = request
        self._request_record = record = WARCRecord()
        record.set_common_fields(WARCRecord.REQUEST, WARCRecord.TYPE_REQUEST)
        record.fields['WARC-Target-URI'] = request.url_info.url
        record.fields['WARC-IP-Address'] = request.address[0]
        record.block_file = self._new_temp_file(hint='warcsesreq')

    def request_data(self, data):
        self._request_record.block_file.write(data)

    def request(self, request):
        payload_offset = len(request.to_bytes())

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
        payload_offset = len(response.to_bytes())

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


class FTPWARCRecorderSession(BaseWARCRecorderSession):
    '''FTP WARC Recorder Session.'''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request = None
        self._control_record = None
        self._response_record = None

    def close(self):
        if self._control_record and self._control_record.block_file:
            self._control_record.block_file.close()

        if self._response_record and self._response_record.block_file:
            self._response_record.block_file.close()

    def begin_control(self, request):
        self._request = request
        self._control_record = record = WARCRecord()

        record.set_common_fields('metadata', 'text/x-ftp-control-conversation')
        record.fields['WARC-Target-URI'] = request.url_info.url
        record.fields['WARC-IP-Address'] = request.address[0]

        record.block_file = self._new_temp_file('warcctrl')

        hostname, port = self._request_hostname_port()

        self._write_control_event(
            'Opening control connection to {hostname}:{port}'
            .format(hostname=hostname, port=port)
        )

    def end_control(self, response):
        hostname, port = self._request_hostname_port()

        self._write_control_event(
            'Closed control connection to {hostname}:{port}'
            .format(hostname=hostname, port=port)
        )

        self._control_record.block_file.seek(0)
        self._recorder.set_length_and_maybe_checksums(self._control_record)
        self._recorder.write_record(self._control_record)

    def request_control_data(self, data):
        text = textwrap_indent(
            data.decode('latin-1'), '> ', predicate=lambda line: True
        )
        self._control_record.block_file.write(text.encode('latin-1'))

        if not data.endswith(b'\n'):
            self._control_record.block_file.write(b'\n')

    def response_control_data(self, data):
        text = textwrap_indent(
            data.decode('latin-1'), '< ', predicate=lambda line: True
        )
        self._control_record.block_file.write(text.encode('latin-1'))

        if not data.endswith(b'\n'):
            self._control_record.block_file.write(b'\n')

    def _write_control_event(self, text):
        text = textwrap_indent(text, '* ', predicate=lambda line: True)
        self._control_record.block_file.write(text.encode('latin-1'))

        if not text.endswith('\n'):
            self._control_record.block_file.write(b'\n')

    def _request_hostname_port(self):
        hostname = self._request.address[0]

        if ':' in hostname:
            hostname = '[{}]'.format(hostname)

        port = self._request.address[1]

        return hostname, port

    def pre_response(self, response):
        hostname, port = response.data_address
        self._write_control_event(
            'Opened data connection to {hostname}:{port}'
            .format(hostname=hostname, port=port)
        )

        self._response_record = record = WARCRecord()
        record.set_common_fields('resource', 'application/octet-stream')
        record.fields['WARC-Target-URI'] = self._request.url_info.url
        record.fields['WARC-IP-Address'] = self._request.address[0]
        record.fields['WARC-Concurrent-To'] = self._control_record.fields[
            WARCRecord.WARC_RECORD_ID]
        record.block_file = self._new_temp_file('warcresp')

    def response_data(self, data):
        self._response_record.block_file.write(data)

    def response(self, response):
        hostname, port = response.data_address
        self._write_control_event(
            'Closed data connection to {hostname}:{port}'
            .format(hostname=hostname, port=port)
        )

        self._response_record.block_file.seek(0)
        self._recorder.set_length_and_maybe_checksums(self._response_record)
        self._recorder.write_record(self._response_record)
