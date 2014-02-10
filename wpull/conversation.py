# encoding=utf-8
'''Protocol interaction session elements.'''
import abc
import os
import tempfile

import wpull.util


class BaseRequest(object, metaclass=abc.ABCMeta):
    '''Base class for Requests.

    This class has no purpose yet.
    '''
    pass


class BaseResponse(object, metaclass=abc.ABCMeta):
    '''Base class for Response.

    This class has no purpose yet.
    '''
    pass


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
        this function is gauranteed to not return more than `max_length` bytes.
        '''
        with wpull.util.reset_file_offset(self.content_file):
            return self.content_file.read(max_length)

    content_segment = content_peek
    '''.. deprecated:: 0.12

       Use :func:`content_peek` instead.
    '''

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
