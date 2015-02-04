# encoding=utf-8
'''HTTP conversation objects.'''
import copy
import re

from wpull.abstract.request import SerializableMixin, DictableMixin, \
    URLPropertyMixin, ProtocolResponseMixin
from wpull.errors import ProtocolError
from wpull.namevalue import NameValueRecord
import wpull.string


class RawRequest(SerializableMixin, DictableMixin):
    '''Represents an HTTP request.

    Attributes:
        method (str): The HTTP method in the status line. For example, ``GET``,
            ``POST``.
        resource_path (str): The URL or "path" in the status line.
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.0``.
        fields (:class:`.namevalue.NameValueRecord`): The fields in
            the HTTP header.
        body (:class:`.body.Body` or file-like): An optional payload.
        encoding (str): The encoding of the status line.
    '''
    def __init__(self, method=None, resource_path=None, version='HTTP/1.1'):
        super().__init__()
        self.method = method
        self.resource_path = resource_path
        self.version = version
        self.fields = NameValueRecord(encoding='latin-1')
        self.body = None
        self.encoding = 'latin-1'

    def to_dict(self):
        return {
            'protocol': 'http',
            'method': self.method,
            'version': self.version,
            'resource_path': self.resource_path,
            'fields': list(self.fields.get_all()),
            'body': self.call_to_dict_or_none(self.body),
            'encoding': self.encoding,
        }

    def to_bytes(self):
        assert self.method
        assert self.resource_path
        assert self.version

        status = '{0} {1} {2}'.format(self.method, self.resource_path, self.version).encode(self.encoding)
        fields = self.fields.to_bytes(errors='replace')

        return b'\r\n'.join([status, fields, b''])

    def parse(self, data):
        if not self.resource_path:
            line, data = data.split(b'\n', 1)
            self.method, self.resource_path, self.version = self.parse_status_line(line)

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
            method=self.method, url=self.resource_path, version=self.version
        )

    def copy(self):
        '''Return a copy.'''
        return copy.deepcopy(self)

    def set_continue(self, offset):
        '''Modify the request into a range request.'''
        assert offset >= 0, offset
        self.fields['Range'] = 'bytes={0}-'.format(offset)


class Request(RawRequest, URLPropertyMixin):
    '''Represents a higher level of HTTP request.

    Attributes:
        address (tuple): An address tuple suitable for :func:`socket.connect`.
        username (str): Username for HTTP authentication.
        password (str): Password for HTTP authentication.
    '''
    def __init__(self, url=None, method='GET', version='HTTP/1.1'):
        super().__init__(method=method, resource_path=url, version=version)

        self.address = None
        self.username = None
        self.password = None

        if url:
            self.url = url

    def to_dict(self):
        dict_obj = super().to_dict()
        dict_obj['url'] = self._url
        dict_obj['url_info'] = self._url_info.to_dict() if self._url_info else None

        return dict_obj

    def prepare_for_send(self, full_url=False):
        '''Modify the request to be suitable for HTTP server.

        Args:
            full_url (bool): Use full URL as the URI. By default, only
                the path of the URL is given to the server.
        '''
        assert self.url
        assert self.method
        assert self.version

        url_info = self.url_info

        if 'Host' not in self.fields:
            self.fields['Host'] = url_info.hostname_with_port

        if not full_url:
            if url_info.query:
                self.resource_path = '{0}?{1}'.format(url_info.path, url_info.query)
            else:
                self.resource_path = url_info.path
        else:
            self.resource_path = url_info.url

    def parse(self, data):
        super().parse(data)

        if not self._url:
            assert self.resource_path

            if self.resource_path[0:1] == '/' and 'Host' in self.fields:
                self.url = 'http://{0}{1}'.format(self.fields['Host'], self.resource_path)
            elif self.resource_path.startswith('http'):
                self.url = self.resource_path


class Response(SerializableMixin, DictableMixin, ProtocolResponseMixin):
    '''Represents the HTTP response.

    Attributes:
        status_code (int): The status code in the status line.
        status_reason (str): The status reason string in the status line.
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.1``.
        fields (:class:`.namevalue.NameValueRecord`): The fields in
            the HTTP headers (and trailer, if present).
        body (:class:`.body.Body` or file-like): The optional payload (without
            and transfer or content encoding).
        request: The corresponding request.
        encoding (str): The encoding of the status line.
    '''
    def __init__(self, status_code=None, reason=None, version='HTTP/1.1', request=None):
        if status_code is not None:
            assert isinstance(status_code, int), \
                'Expect int, got {}'.format(type(status_code))
            assert reason is not None

        self.status_code = status_code
        self.reason = reason
        self.version = version
        self.fields = NameValueRecord(encoding='latin-1')
        self.body = None
        self.request = request
        self.encoding = 'latin-1'

    @property
    def protocol(self):
        return 'http'

    def to_dict(self):
        return {
            'protocol': 'http',
            'status_code': self.status_code,
            'reason': self.reason,
            'response_code': self.status_code,
            'response_message': self.reason,
            'version': self.version,
            'fields': list(self.fields.get_all()),
            'body': self.call_to_dict_or_none(self.body),
            'request': self.request.to_dict() if self.request else None,
            'encoding': self.encoding,
        }

    def to_bytes(self):
        assert self.version
        assert self.status_code is not None
        assert self.reason is not None

        status = '{0} {1} {2}'.format(self.version, self.status_code, self.reason).encode(self.encoding)
        fields = self.fields.to_bytes(errors='replace')

        return b'\r\n'.join([status, fields, b''])

    def parse(self, data):
        if self.status_code is None:
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

        raise ProtocolError(
            'Error parsing status line {line}".'.format(line=ascii(data))
        )

    def __repr__(self):
        return '<Response({version}, {code}, {reason})>'.format(
            version=ascii(self.version), code=self.status_code,
            reason=ascii(self.reason)
        )

    def __str__(self):
        return wpull.string.printable_str(
            self.to_bytes().decode('utf-8', 'replace'), keep_newlines=True
        )

    def response_code(self):
        return self.status_code

    def response_message(self):
        return self.reason
