# encoding=utf-8
'''Document readers.'''
import abc
import gzip
import io
import lxml.html
import re
import zlib

import wpull.http.util
from wpull.thirdparty import robotexclusionrulesparser
import wpull.util


class BaseDocumentReader(object, metaclass=abc.ABCMeta):
    '''Base class for classes that read documents.'''

    @abc.abstractmethod
    def parse(self, file):
        '''Read and return a document.

        The arguments and return value will depend on the implementation.
        '''
        pass

    @classmethod
    def is_supported(cls, file):
        '''Return whether the reader is likely able to read the document.

        The arguments will depend on the implementation.

        Returns:
            bool: If True, reader should be able to read it.
        '''
        # Python 2.6 doesn't support abc.abstractclassmethod
        raise NotImplementedError()


class HTMLReader(BaseDocumentReader):
    '''HTML document reader.

    This reader uses lxml as the parser.
    '''
    def parse(self, file, encoding=None, base_url=None):
        '''Parse the HTML file and return the document.

        Args:
            file: A file object.
            encoding (str): If provided, it will override the encoding
                specified in the document.
            base_url (str): If provided, it will override the base URL
                specified in the document.

        Returns:
            _ElementTree: An instance of :class:`lxml.etree._ElementTree`.
        '''
        if encoding:
            lxml_encoding = to_lxml_encoding(encoding) or 'latin1'

# FIXME: this needs more testing
#             if not lxml_encoding:
#                 parser = lxml.html.HTMLParser()
#
#                 with wpull.util.reset_file_offset(file):
#                     decoded_file = io.StringIO(file.read().decode(encoding))
#                     tree = lxml.html.parse(
#                         decoded_file,
#                         base_url=base_url,
#                         parser=parser,
#                     )
#
#                 return tree
        else:
            lxml_encoding = encoding

        parser = lxml.html.HTMLParser(encoding=lxml_encoding)

        with wpull.util.reset_file_offset(file):
            tree = lxml.html.parse(
                file,
                base_url=base_url,
                parser=parser,
            )
            return tree

    @classmethod
    def is_supported(cls, file, request=None, response=None, url_info=None):
        '''Return whether the file is likely to be HTML.'''
        if response and cls.is_html_response(response) \
        or request and cls.is_html_request(request) \
        or url_info and cls.is_html_url_info(url_info):
            return True

        if cls.is_html_file(file):
            return True

    @classmethod
    def is_html(cls, request, response):
        '''Return whether Request/Response is likely to be HTML.'''
        return cls.is_html_request(request) or cls.is_html_response(response)

    @classmethod
    def is_html_response(cls, response):
        '''Return whether the Response is likely to be HTML.'''
        if 'html' in response.fields.get('content-type', '').lower():
            return True

        if response.body:
            return cls.is_html_file(response.body.content_file)

    @classmethod
    def is_html_request(cls, request):
        '''Return whether the Request is likely to be a HTML.'''
        return cls.is_html_url_info(request.url_info)

    @classmethod
    def is_html_url_info(cls, url_info):
        '''Return whether the URLInfo is likely to be a HTML.'''
        path = url_info.path.lower()
        if '.htm' in path or '.dhtm' in path:
            return True

    @classmethod
    def is_html_file(cls, file):
        '''Return whether the file is likely to be HTML.'''
        peeked_data = wpull.util.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<!doctype html' in peeked_data \
        or b'<head' in peeked_data \
        or b'<title' in peeked_data \
        or b'<html' in peeked_data \
        or b'<script' in peeked_data \
        or b'<table' in peeked_data \
        or b'<a href' in peeked_data:
            return True


class CSSReader(BaseDocumentReader):
    '''Cascading Stylesheet Document Reader.'''
    def parse(self, *args, **kwargs):
        raise NotImplementedError()

    @classmethod
    def is_supported(cls, file, request=None, response=None, url_info=None):
        '''Return whether the file is likely to be CSS.'''
        if request and cls.is_css_request(request) \
        or response and cls.is_css_response(response) \
        or url_info and cls.is_css_url_info(url_info):
            return True

        return cls.is_css_file(file)

    @classmethod
    def is_css(cls, request, response):
        '''Return whether the document is likely to be CSS.'''
        if cls.is_css_request(request) or cls.is_css_response(response):
            return True

        if response.body:
            if 'html' in response.fields.get('content-type', '').lower() \
            and cls.is_css_file(response.body.content_file):
                return True

    @classmethod
    def is_css_url_info(cls, url_info):
        '''Return whether the document is likely to be CSS.'''
        if '.css' in url_info.path.lower():
            return True

    @classmethod
    def is_css_request(cls, request):
        '''Return whether the document is likely to be CSS.'''
        return cls.is_css_url_info(request.url_info)

    @classmethod
    def is_css_response(cls, response):
        '''Return whether the document is likely to be CSS.'''
        if 'css' in response.fields.get('content-type', '').lower():
            return True

    @classmethod
    def is_css_file(cls, file):
        '''Return whether the file is likely CSS.'''
        peeked_data = wpull.util.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<html' in peeked_data:
            return False

        if re.search(br'@import |color:|background[a-z-]*:|font[a-z-]*:',
        peeked_data):
            return True


class SitemapReader(BaseDocumentReader):
    def parse(self, file, encoding=None):
        '''Parse Sitemap.

        Returns:
            RobotExclusionRulesParser, ElementTree
        '''
        peeked_data = wpull.util.peek_file(file)

        if wpull.document.is_gzip(peeked_data):
            file = gzip.GzipFile(mode='rb', fileobj=file)

        if self.is_sitemap_file(file):
            if encoding:
                lxml_encoding = to_lxml_encoding(encoding) or 'latin1'

# FIXME: this needs better testing
#                 if not lxml_encoding:
#                     parser = lxml.etree.XMLParser()
#
#                     with wpull.util.reset_file_offset(file):
#                         decoded_file = io.StringIO(file.read().decode(encoding))
#
#                     tree = lxml.etree.parse(decoded_file, parser=parser)
#                     return tree

            else:
                lxml_encoding = encoding

            parser = lxml.etree.XMLParser(encoding=lxml_encoding)

            with wpull.util.reset_file_offset(file):
                tree = lxml.etree.parse(
                    file,
                    parser=parser,
                )
                return tree
        else:
            parser = robotexclusionrulesparser.RobotExclusionRulesParser()
            parser.parse(file.read())

            return parser

    @classmethod
    def is_supported(cls, file, request=None, url_info=None):
        if request and cls.is_sitemap_request(request) \
        or url_info and cls.is_sitemap_url_info(url_info):
            return True

        return cls.is_sitemap_file(file)

    @classmethod
    def is_sitemap(cls, request, response):
        '''Return whether the document is likely to be a Sitemap.'''
        if cls.is_sitemap_request(request):
            return True

        if response.body:
            if cls.is_sitemap_file(response.body.content_file):
                return True

    @classmethod
    def is_sitemap_url_info(cls, url_info):
        '''Return whether the document is likely to be a Sitemap.'''
        path = url_info.path.lower()
        if path == '/robots.txt':
            return True
        if 'sitemap' in path and '.xml' in path:
            return True

    @classmethod
    def is_sitemap_request(cls, request):
        '''Return whether the document is likely to be a Sitemap.'''
        return cls.is_sitemap_url_info(request.url_info)

    @classmethod
    def is_sitemap_file(cls, file):
        '''Return whether the file is likely a Sitemap.'''
        peeked_data = wpull.util.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if is_gzip(peeked_data):
            try:
                peeked_data = wpull.util.gzip_uncompress(peeked_data)
            except zlib.error:
                pass

        peeked_data = peeked_data.replace(b'\x00', b'')

        if b'<?xml' in peeked_data \
        and (b'<sitemapindex' in peeked_data or b'<urlset' in peeked_data):
            return True


def get_heading_encoding(response):
    '''Return the document encoding from a HTTP header.

    Args:
        response (Response): An instance of :class:`.http.Response`.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.util.parse_charset(
        response.fields.get('content-type', ''))

    if encoding:
        return wpull.util.normalize_codec_name(encoding)
    else:
        return None


def get_encoding(response, is_html=False, peek=10485760):
    '''Return the likely encoding of the document.

    Args:
        response (Response): An instance of :class:`.http.Response`.
        is_html (bool): See :func:`.util.detect_encoding`.
        peek (int): The number of bytes to read of the document.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.util.parse_charset(
        response.fields.get('content-type', '')
    )

    encoding = wpull.util.detect_encoding(
        response.body.content_peek(peek), encoding=encoding, is_html=is_html
    )

    return encoding


def is_gzip(data):
    '''Return whether the data is likely to be gzip.'''
    return data.startswith(b'\x1f\x8b')


def to_lxml_encoding(encoding):
    '''Check if lxml supports the specified encoding.

    Returns:
        str, None
    '''
    # XXX: Workaround lxml not liking utf-16-le
    try:
        lxml.html.HTMLParser(encoding=encoding)
    except LookupError:
        encoding = encoding.replace('-', '')
    else:
        return encoding
    try:
        lxml.html.HTMLParser(encoding=encoding)
    except LookupError:
        encoding = encoding.replace('_', '')
    else:
        return encoding

    try:
        lxml.html.HTMLParser(encoding=encoding)
    except LookupError:
        pass
    else:
        return encoding
