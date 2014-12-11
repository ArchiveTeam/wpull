# encoding=utf-8
'''WARC format.

For the WARC file specification, see
http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf.

For the CDX specifications, see
https://archive.org/web/researcher/cdx_file_format.php and
https://github.com/internetarchive/CDX-Writer.
'''
import base64
import codecs
import hashlib
import re
import uuid

from wpull.http.request import Response
from wpull.namevalue import NameValueRecord
import wpull.util


class WARCRecord(object):
    '''A record in a WARC file.

    Attributes:
        fields: An instance of :class:`.namevalue.NameValueRecord`.
        block_file: A file object. May be None.
    '''
    VERSION = 'WARC/1.0'
    WARC_TYPE = 'WARC-Type'
    CONTENT_TYPE = 'Content-Type'
    WARC_DATE = 'WARC-Date'
    WARC_RECORD_ID = 'WARC-Record-ID'
    WARCINFO = 'warcinfo'
    WARC_FIELDS = 'application/warc-fields'
    REQUEST = 'request'
    RESPONSE = 'response'
    REVISIT = 'revisit'
    TYPE_REQUEST = 'application/http;msgtype=request'
    TYPE_RESPONSE = 'application/http;msgtype=response'
    SAME_PAYLOAD_DIGEST_URI = \
        'http://netpreserve.org/warc/1.0/revisit/identical-payload-digest'
    NAME_OVERRIDES = frozenset([
        'WARC-Date',
        'WARC-Type',
        'WARC-Record-ID',
        'WARC-Concurrent-To',
        'WARC-Refers-To',
        'Content-Length',
        'Content-Type',
        'WARC-Target-URI',
        'WARC-Block-Digest',
        'WARC-IP-Address',
        'WARC-Filename',
        'WARC-Warcinfo-ID',
        'WARC-Payload-Digest',
        'WARC-Truncated',
        'WARC-Filename',
        'WARC-Profile',
        'WARC-Identified-Payload-Type',
        'WARC-Segment-Origin-ID',
        'WARC-Segment-Number',
        'WARC-Segment-Total-Length',
    ])
    '''Field name case normalization overrides because hanzo's warc-tools do
    not adequately conform to specifications.'''

    def __init__(self):
        self.fields = NameValueRecord(normalize_overrides=self.NAME_OVERRIDES)
        self.block_file = None

    def set_common_fields(self, warc_type, content_type):
        '''Set the required fields for the record.'''
        self.fields[self.WARC_TYPE] = warc_type
        self.fields[self.CONTENT_TYPE] = content_type
        self.fields[self.WARC_DATE] = wpull.util.datetime_str()
        self.fields[self.WARC_RECORD_ID] = '<{0}>'.format(uuid.uuid4().urn)

    def set_content_length(self):
        '''Find and set the content length.

        .. seealso:: :meth:`compute_checksum`.
        '''
        if not self.block_file:
            self.fields['Content-Length'] = '0'
            return

        with wpull.util.reset_file_offset(self.block_file):
            self.block_file.seek(0, 2)
            self.fields['Content-Length'] = str(self.block_file.tell())

    def compute_checksum(self, payload_offset=None):
        '''Compute and add the checksum data to the record fields.

        This function also sets the content length.
        '''
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
        '''Iterate the record as bytes.'''
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

    def __bytes__(self):
        '''Return the record as bytes.'''
        return b''.join(iter(self))

    def get_http_header(self):
        '''Return the HTTP header.

        It only attempts to read the first 4 KiB of the payload.

        Returns:
            Response, None: Returns an instance of
            :class:`.http.request.Response` or None.
        '''
        with wpull.util.reset_file_offset(self.block_file):
            data = self.block_file.read(4096)

        match = re.match(br'(.*?\r?\n\r?\n)', data)

        if not match:
            return

        status_line, dummy, field_str = match.group(1).partition(b'\n')

        try:
            version, code, reason = Response.parse_status_line(status_line)
        except ValueError:
            return

        response = Response(status_code=code, reason=reason, version=version)

        try:
            response.fields.parse(field_str, strict=False)
        except ValueError:
            return

        return response


def read_cdx(file, encoding='utf8'):
    '''Iterate CDX file.

    Args:
        file (str): A file object.
        encoding (str): The encoding of the file.

    Returns:
        iterator: Each item is a dict that maps from field key to value.
    '''
    with codecs.getreader(encoding)(file) as stream:
        header_line = stream.readline()
        separator = header_line[0]
        field_keys = header_line.strip().split(separator)

        if field_keys.pop(0) != 'CDX':
            raise ValueError('CDX header not found.')

        for line in stream:
            yield dict(zip(field_keys, line.strip().split(separator)))
