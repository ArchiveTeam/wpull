# encoding=utf-8
'''HTTP conversation objects.'''
import abc
import re

from wpull.errors import ProtocolError
from wpull.namevalue import NameValueRecord
import wpull.string
from wpull.url import URLInfo


class CommonMixin(object):
    @abc.abstractmethod
    def to_dict(self):
        '''Convert to a dict suitable for JSON.'''

    @abc.abstractmethod
    def to_bytes(self):
        '''Serialize to HTTP bytes.'''

    @abc.abstractmethod
    def parse(self, data):
        '''Parse from HTTP bytes.'''


class Request(CommonMixin):
    '''Represents an HTTP request.

    Attributes:
        uri (str): The URL or "path" in the status line.
        method (str): The HTTP method in the status line. For example, ``GET``,
            ``POST``.
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.0``.
        fields (NameValueRecord): An instance of
            :class:`.namevalue.NameValueRecord` representing  the fields in
            the HTTP header.
        body (Body): An instance of :class:`.conversation.Body`.
        encoding (str): The encoding of the status line.
        url_info (URLInfo): An instance of :class:`.url.URLInfo` for the
            request.
        address (tuple): An address tuple suitable for :func:`socket.connect`.
    '''
    def __init__(self, uri=None, method='GET', version='HTTP/1.1'):
        self.uri = uri
        self.method = method
        self.version = version
        self.fields = NameValueRecord()
        self.body = None
        self.encoding = 'latin-1'

        self.url_info = None
        self.address = None

    def to_dict(self):
        return {
            'uri': self.uri,
            'method': self.method,
            'version': self.version,
            'fields': list(self.fields.get_all()),
            'body': self.body.to_dict() if self.body else None,
            'encoding': self.encoding,
            'url_info': self.url_info.to_dict(),
        }

    def prepare_for_send(self, full_url=False):
        '''Modify the request to be suitable for HTTP server.

        Args:
            full_url (bool): Use full URL as the URI. By default, only
                the path of the URL is given to the server.
        '''
        assert self.uri
        assert self.method
        assert self.version

        if not self.url_info:
            self.url_info = URLInfo.parse(self.uri)

        url_info = self.url_info

        if 'Host' not in self.fields:
            self.fields['Host'] = url_info.hostname_with_port

        if not full_url:
            if url_info.query:
                self.uri = '{0}?{1}'.format(url_info.path, url_info.query)
            else:
                self.uri = url_info.path

    def to_bytes(self):
        status = '{0} {1} {2}'.format(self.method, self.uri, self.version).encode(self.encoding)
        fields = bytes(self.fields)

        return b'\r\n'.join([status, fields, b''])

    def parse(self, data):
        if not self.method:
            line, data = data.split(b'\n', 1)
            self.method, self.uri, self.version = self.parse_status_line(line)

        self.fields.parse(data, strict=False)

    def parse_status_line(self, data):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the method, URI, and
            version.
        '''
        match = re.match(
            br'([a-zA-Z]+)[ \t]+([^ \t]+)[ \t]+(HTTP/\d+\.\d+)',
            data
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return wpull.string.to_str(
                    (groups[0], groups[1], groups[2]),
                    encoding=self.encoding,
                )

        raise ProtocolError('Error parsing status line.')

    def __repr__(self):
        return '<Request({method}, {url}, {version})>'.format(
            method=self.method, url=self.uri, version=self.version
        )


class Response(CommonMixin):
    '''Represents the HTTP response.

    Attributes:
        status_code (int): The status code in the status line.
        status_reason (str): The status reason string in the status line.
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.1``.
        fields (NameValueRecord): An instance of
            :class:`.namevalue.NameValueRecord` containing the HTTP header
            (and trailer, if present) fields.
        body (Body): An instance of :class:`.conversation.Body`.
        request: The corresponding request.
        encoding (str): The encoding of the status line.
    '''
    def __init__(self, status_code=None, reason=None, version=None, request=None):
        self.status_code = status_code
        self.reason = reason
        self.version = version
        self.fields = NameValueRecord()
        self.body = None
        self.request = request
        self.encoding = 'latin-1'

    def to_dict(self):
        return {
            'status_code': self.status_code,
            'reason': self.reason,
            'version': self.version,
            'fields': list(self.fields.get_all()),
            'body': self.body.to_dict() if self.body else None,
            'request': self.request.to_dict() if self.request else None,
            'encoding': self.encoding,
        }

    def to_bytes(self):
        status = '{0} {1} {2}'.format(self.version, self.status_code, self.reason).encode(self.encoding)
        fields = bytes(self.fields)

        return b'\r\n'.join([status, fields, b''])

    def parse(self, data):
        if not self.status_code:
            line, data = data.split(b'\n', 1)
            self.version, self.status_code, self.reason = self.parse_status_line(line)

        self.fields.parse(data, strict=False)

    @classmethod
    def parse_status_line(cls, data):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the version, code, and reason.
        '''
        match = re.match(
            br'(HTTP/\d+\.\d+)[ \t]+([0-9]{1,3})[ \t]*([^\r\n]*)',
            data
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return wpull.string.to_str(
                    (groups[0], int(groups[1]), groups[2]),
                    encoding='latin-1',
                )

        raise ProtocolError('Error parsing status line.')

    def __repr__(self):
        return '<Response({version}, {code}, {reason})>'.format(
            version=self.version, code=self.status_code,
            reason=self.status_reason
        )
