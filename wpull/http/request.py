# encoding=utf-8
'''HTTP conversation objects.'''
import re

from wpull.conversation import BaseRequest, Body, BaseResponse
from wpull.errors import ProtocolError
from wpull.namevalue import NameValueRecord
import wpull.string
from wpull.url import URLInfo
import wpull.util


class Request(BaseRequest):
    '''Represents an HTTP request.

    Attributes:
        method (str): The HTTP method in the status line. For example, ``GET``,
            ``POST``.
        resource_url (str): The "path" in the status line.
        url_info (URLInfo): An instance of :class:`.url.URLInfo` for the
            request.
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.0``.
        fields (NameValueRecord): An instance of
            :class:`.namevalue.NameValueRecord` representing  the fields in
            the HTTP header.
        body (Body): An instance of :class:`.conversation.Body`.
        address (tuple): An address tuple suitable for :func:`socket.connect`.
    '''
    def __init__(self, method, resource_url, version='HTTP/1.1'):
        self.method = method
        self.resource_url = resource_url
        self.url_info = None
        self.version = version
        self.fields = NameValueRecord()
        self.body = Body()
        self.address = None

    @classmethod
    def new(cls, url, method='GET', url_encoding='utf-8'):
        '''Create a new request from the URL string.

        Args:
            url (str): The URL.
            method (str): The HTTP request method.
            url_encoding (str): The codec name used to encode/decode the
                percent-encoded escape sequences in the URL.

        Returns:
            Request: An instance of :class:`Request`.
        '''
        url_info = URLInfo.parse(url, encoding=url_encoding)
        resource_path = url_info.path

        if url_info.query:
            resource_path += '?' + url_info.query

        request = Request(method.upper(), resource_path)
        request.url_info = url_info
        request.fields['Host'] = url_info.hostname_with_port

        return request

    @classmethod
    def parse_status_line(cls, string):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the method, resource path, and
            version.
        '''
        match = re.match(
            br'([a-zA-Z]+)[ \t]+([^ \t]+)[ \t]+(HTTP/1\.[01])',
            string
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return wpull.string.to_str(
                    (groups[0], groups[1], groups[2]),
                    encoding='latin-1',
                )

        raise ProtocolError('Error parsing status line ‘{0}’'.format(string))

    def header(self):
        '''Return the HTTP header as bytes.'''
        return '{0} {1} {2}\r\n{3}\r\n'.format(
            self.method, self.resource_url, self.version, str(self.fields)
        ).encode('utf-8')

    def __repr__(self):
        return '<Request({method}, {url}, {version})>'.format(
            method=self.method, url=self.resource_url, version=self.version
        )


class Response(BaseResponse):
    '''Represents the HTTP response.

    Attributes:
        version (str): The HTTP version in the status line. For example,
            ``HTTP/1.1``.
        status_code (int): The status code in the status line.
        status_reason (str): The status reason string in the status line.
        fields (NameValueRecord): An instance of
            :class:`.namevalue.NameValueRecord` containing the HTTP header
            (and trailer, if present) fields.
        body (Body): An instance of :class:`.conversation.Body`.
        url_info (URLInfo): An instance of :class:`.url.URLInfo` for the
            of the corresponding request.
    '''
    def __init__(self, version, status_code, status_reason):
        self.version = version
        self.status_code = status_code
        self.status_reason = status_reason
        self.fields = NameValueRecord()
        self.body = Body()
        self.url_info = None

    @classmethod
    def parse_status_line(cls, string):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the version, code, and reason.
        '''
        match = re.match(
            br'(HTTP/1\.[01])[ \t]+([0-9]{1,3})[ \t]*([^\r\n]*)',
            string
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                return wpull.string.to_str(
                    (groups[0], int(groups[1]), groups[2]),
                    encoding='latin-1',
                )

        raise ProtocolError("Error parsing status line '{0}'".format(string))

    def header(self):
        '''Return the HTTP header as bytes.'''
        return '{0} {1} {2}\r\n{3}\r\n'.format(
            self.version,
            self.status_code,
            self.status_reason,
            str(self.fields)
        ).encode('utf-8')

    def __repr__(self):
        return '<Response({version}, {code}, {reason})>'.format(
            version=self.version, code=self.status_code,
            reason=self.status_reason
        )

    def to_dict(self):
        '''Convert the response to a :class:`dict`.'''
        return {
            'version': self.version,
            'status_code': self.status_code,
            'status_reason': self.status_reason,
            'body': self.body.to_dict(),
            'url_info': self.url_info.to_dict() if self.url_info else None
        }
