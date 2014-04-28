# encoding=utf-8
'''HTTP conversation objects.'''
import re

from wpull.conversation import BaseRequest, BaseResponse
from wpull.errors import ProtocolError
import wpull.string
from wpull.url import URLInfo


class Request(BaseRequest):
    '''Represents an HTTP request.'''
    def __init__(self, method=None, resource_name=None, version='HTTP/1.1'):
        super().__init__(version, method, resource_name)

    @property
    def version(self):
        '''An alias of :attr:`protocol`.'''
        return self.protocol

    @version.setter
    def version(self, new_ver):
        self.protocol = new_ver

    @classmethod
    def new(cls, url, method='GET', url_encoding='utf-8'):
        '''Create a new request from a URL string.

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
        request.encoding = 'utf-8'

        return request

    @classmethod
    def parse_status_line(cls, string, encoding='utf-8',
    fallback_encoding='latin-1'):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the method, resource name,
            version, and character encoding of the resource name.
        '''
        match = re.match(
            br'([a-zA-Z]+)[ \t]+([^ \t]+)[ \t]+(HTTP/1\.[01])',
            string
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                try:
                    return wpull.string.to_str(
                        (groups[0], groups[1], groups[2], encoding),
                        encoding=encoding
                    )
                except UnicodeError:
                    return wpull.string.to_str(
                        (groups[0], groups[1], groups[2], fallback_encoding),
                        encoding=fallback_encoding
                    )

        raise ProtocolError('Error parsing status line.')

    def parse(self, data):
        '''Parse the HTTP status line.'''
        (self.method,
            self.resource_name,
            self.version,
            self.encoding
        ) = self.parse_status_line(data)

    def to_str(self):
        '''Return the HTTP status line as a string.'''
        return '{0} {1} {2}\r\n{3}\r\n'.format(
            self.method, self.resource_name, self.version, str(self.fields)
        )

    def to_bytes(self):
        '''Return the HTTP status line as bytes.'''
        status_line = '{0} {1} {2}\r\n'.format(
            self.method, self.resource_name, self.version
        ).encode(self.encoding)
        fields = '{0}\r\n'.format(str(self.fields))\
            .encode(self.fields.encoding)

        return status_line + fields


class Response(BaseResponse):
    '''Represents the HTTP response.'''
    def __init__(self, version=None, status_code=None, status_reason=None):
        super().__init__(version, status_code, status_reason)

    @property
    def version(self):
        '''An alias of :attr:`protocol`.'''
        return self.protocol

    @version.setter
    def version(self, new_ver):
        self.protocol = new_ver

    @classmethod
    def parse_status_line(cls, string, encoding='utf-8',
    fallback_encoding='latin-1'):
        '''Parse the status line bytes.

        Returns:
            tuple: An tuple representing the version, status code,
            status reason, and character encoding of the status reason.
        '''
        match = re.match(
            br'(HTTP/1\.[01])[ \t]+([0-9]{1,3})[ \t]*([^\r\n]*)',
            string
        )
        if match:
            groups = match.groups()
            if len(groups) == 3:
                try:
                    return wpull.string.to_str(
                        (groups[0], int(groups[1]), groups[2], encoding),
                        encoding=encoding
                    )
                except UnicodeError:
                    return wpull.string.to_str(
                        (groups[0], int(groups[1]), groups[2],
                            fallback_encoding),
                        encoding=fallback_encoding
                    )

        raise ProtocolError('Error parsing status line.')

    def parse(self, data):
        '''Parse the HTTP status line.'''
        (self.version,
            self.status_code,
            self.status_reason,
            self.encoding
        ) = self.parse_status_line(data)

    def to_str(self):
        '''Return the HTTP status line as a string.'''
        return '{0} {1} {2}\r\n{3}\r\n'.format(
            self.version,
            self.status_code,
            self.status_reason,
            str(self.fields)
        )

    def to_bytes(self):
        '''Return the HTTP status line as bytes.'''
        status_line = '{0} {1} {2}\r\n'.format(
            self.version,
            self.status_code,
            self.status_reason,
        ).encode(self.encoding)
        fields = '{0}\r\n'.format(str(self.fields))\
            .encode(self.fields.encoding)
        return status_line + fields

    def to_dict(self):
        info_dict = super().to_dict()
        info_dict['version'] = self.version
        return info_dict
