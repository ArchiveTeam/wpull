# encoding=utf-8
'''Document readers.'''
import abc
import codecs
import lxml.html

import wpull.util


class BaseDocumentReader(object, metaclass=abc.ABCMeta):
    '''Base class for classes that read documents.'''

    @abc.abstractmethod
    def parse(self, file):
        '''Read and return a document.

        The arguments and return value will depend on the implementation
        '''
        pass


class HTMLReader(BaseDocumentReader):
    def parse(self, file, encoding=None, base_url=None):
        parser = lxml.html.HTMLParser(encoding=encoding)

        with wpull.util.reset_file_offset(file):
            tree = lxml.html.parse(
                file,
                base_url=base_url,
                parser=parser,
            )
            return tree.getroot()


def get_heading_encoding(response):
    '''Return the document encoding from a HTTP header.

    Args:
        response (Response): An instance of :class:`.http.Response`.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.parse_charset(
        response.fields.get('content-type', ''))

    if encoding:
        try:
            codec = codecs.lookup(encoding)
        except LookupError:
            return None
        else:
            return codec.name
    else:
        return None


def get_encoding(response):
    '''Return the likely encoding of the document.

    Args:
        response (Response): An instance of :class:`.http.Response`.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.parse_charset(
        response.fields.get('content-type', ''))

    encoding = wpull.util.detect_encoding(response.body.content, encoding)

    return encoding
