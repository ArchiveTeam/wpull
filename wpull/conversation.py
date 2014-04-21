# encoding=utf-8
'''Protocol interaction session elements.'''
import abc
import os
import tempfile

from wpull.namevalue import NameValueRecord
import wpull.util


class BaseRequest(object, metaclass=abc.ABCMeta):
    '''Abstract representation of a request.

    Attributes:
        protocol (str): The protocol name and maybe version. For HTTP, the
            value is typically ``HTTP/1.0`` or ``HTTP/1.1. For FTP, the value
            is typically ``FTP``.
        method (str): The name of the command for an operation. For example,
            ``GET``, ``POST``, ``CWD``.
        resource_name (str): The name of the resource. This can be a path or
            a URL depending on the protocol.
        encoding (str): The character encoding of the `resource_name`.
        fields (:class:`.namevalue.NameValueRecord`): The fields in the
            HTTP header. For other protocols, this may be empty.
        body (:class:`Body`): The optional payload of the request.
        url_info (:class:`.url.URLInfo`): The complete URL for the request.
        address (tuple): An address tuple suitable for :func:`socket.connect`.
    '''
    def __init__(self, protocol=None, method=None, resource_name=None):
        self.protocol = protocol
        self.method = method
        self.resource_name = resource_name
        self.encoding = 'utf-8'
        self.fields = NameValueRecord()
        self.body = Body()
        self.url_info = None
        self.address = None

    @abc.abstractmethod
    def parse(self, data):
        '''Parse the request.'''
        pass

    @abc.abstractmethod
    def to_str(self):
        '''Format the request to a string.

        Returns:
            str
        '''
        pass

    @abc.abstractmethod
    def to_bytes(self):
        '''Format the request to bytes.

        Returns:
            bytes
        '''
        pass

    def __repr__(self):
        return '<Request({protocol}, {method}, {resource})>'.format(
            protocol=self.protocol, method=self.method,
            resource=self.resource_name
        )


class BaseResponse(object, metaclass=abc.ABCMeta):
    '''Abstract representation of a response.

     Attributes:
        protocol (str): The protocol name and maybe version. For HTTP, the
            value is typically ``HTTP/1.0`` or ``HTTP/1.1. For FTP, the value
            is typically ``FTP``.
        status_code (int): The status code in the status line.
        status_reason (str): The status reason string in the status line.
        encoding (str): The character encoding of the `status_reason`.
        fields (:class:`.namevalue.NameValueRecord`): The fields in the
            HTTP header (and trailers if present).
            For other protocols, this may be empty.
        body (:class:`Body`): The optional payload of the response.
        url_info (:class:`.url.URLInfo`): The complete URL for the response.
    '''
    def __init__(self, protocol=None, status_code=None, status_reason=None):
        self.protocol = protocol
        self.status_code = status_code
        self.status_reason = status_reason
        self.encoding = 'utf-8'
        self.fields = NameValueRecord()
        self.body = Body()
        self.url_info = None

    @abc.abstractmethod
    def parse(self, data):
        '''Parse the response.'''
        pass

    @abc.abstractmethod
    def to_str(self):
        '''Format the request to a string.

        Returns:
            str
        '''
        pass

    @abc.abstractmethod
    def to_bytes(self):
        '''Format the request to bytes.

        Returns:
            bytes
        '''
        pass

    def __repr__(self):
        return '<Response({protocol}, {code}, {reason})>'.format(
            protocol=self.protocol, code=self.status_code,
            reason=self.status_reason
        )

    def to_dict(self):
        '''Convert the response to a :class:`dict`.'''
        return {
            'protocol': self.protocol,
            'status_code': self.status_code,
            'status_reason': self.status_reason,
            'body': self.body.to_dict() if self.body else None,
            'url_info': self.url_info.to_dict() if self.url_info else None,
            'encoding': self.encoding,
        }


class Body(object, metaclass=abc.ABCMeta):
    '''Represents the document of a request.

    This class is a wrapper around a file object. The document within the
    file should not contain any content or transfer encodings.

    You can iterate this instance to return the content bytes.

    Attributes:
        content_file (file): A file object containing the document.

    Args:
        content_file (file): Use the given `content_file` as the file object.
    '''
    def __init__(self, content_file=None):
        self.content_file = content_file or self.new_temp_file()
        self._content_data = None

    def __iter__(self):
        with wpull.util.reset_file_offset(self.content_file):
            while True:
                data = self.content_file.read(4096)
                if not data:
                    break
                yield data

    @property
    def content(self):
        '''Return the content of the file.

        If this property is invoked, the contents of the entire file is read
        and cached.

        Returns:
            ``bytes``: The entire content of the file.
        '''
        if not self._content_data:
            with wpull.util.reset_file_offset(self.content_file):
                self._content_data = self.content_file.read()

        return self._content_data

    def content_peek(self, max_length=4096):
        '''Return only a partial part of the file.

        Args:
            max_length (int): The amount to read.

        This function is different different from the standard peek where
        this function is guaranteed to not return more than `max_length` bytes.
        '''
        with wpull.util.reset_file_offset(self.content_file):
            return self.content_file.read(max_length)

    @classmethod
    def new_temp_file(cls, directory=None):
        '''Return a new temporary file.'''
        return tempfile.SpooledTemporaryFile(
            max_size=4194304, prefix='wpull-', suffix='.tmp', dir=directory)

    @property
    def content_size(self):
        '''Return the size of the file.'''
        with wpull.util.reset_file_offset(self.content_file):
            self.content_file.seek(0, os.SEEK_END)
            return self.content_file.tell()

    def to_dict(self):
        '''Convert the body to a :class:`dict`.

        Returns:
            dict: The items are:

                * ``filename`` (string): The path of the file.
                * ``content_size`` (int): The size of the file.
        '''
        if not hasattr(self.content_file, 'name'):
            # Make SpooledTemporaryFile rollover to real file
            self.content_file.fileno()

        return {
            'filename': self.content_file.name,
            'content_size': self.content_size,
        }


class BaseClient(object, metaclass=abc.ABCMeta):
    '''Base class for clients.

    This class has no purpose yet.
    '''
    pass
