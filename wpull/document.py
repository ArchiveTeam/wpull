# encoding=utf-8
'''Document readers.'''
import abc
import codecs
import gzip
import io
import itertools
import json
import logging
import re
import zlib

import lxml.etree
import lxml.html

import wpull.decompression
import wpull.http.util
import wpull.string
from wpull.thirdparty import robotexclusionrulesparser
import wpull.util


_logger = logging.getLogger(__name__)


class BaseDocumentDetector(object, metaclass=abc.ABCMeta):
    '''Base class for classes that detect document types.'''

    @classmethod
    def is_supported(cls, file=None, request=None, response=None,
    url_info=None):
        '''Given the hints, return whether the document is supported.

        Args:
            file: A file object containing the document.
            request (:class:`.http.request.Request`): An HTTP request.
            response (:class:`.http.request.Response`): An HTTP response.
            url_info (:class:`.url.URLInfo`): A URLInfo.

        Returns:
            bool: If True, the reader should be able to read it.
        '''
        if response:
            try:
                if cls.is_response(response):
                    return True
            except NotImplementedError:
                pass

        if file:
            try:
                if cls.is_file(file):
                    return True
            except NotImplementedError:
                pass

        if request:
            try:
                if cls.is_request(request):
                    return True
            except NotImplementedError:
                pass

        if url_info:
            try:
                if cls.is_url(url_info):
                    return True
            except NotImplementedError:
                pass

    @classmethod
    def is_file(cls, file):
        '''Return whether the reader is likely able to read the file.

        Args:
            file: A file object containing the document.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_request(cls, request):
        '''Return whether the request is likely supported.

        Args:
            request (:class:`.http.request.Request`): An HTTP request.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_response(cls, response):
        '''Return whether the response is likely able to be read.

        Args:
            response (:class:`.http.request.Response`): An HTTP response.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the URL is likely to be supported.

        Args:
            url_info (:class:`.url.URLInfo`): A URLInfo.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override


class BaseDocumentReader(BaseDocumentDetector):
    '''Base class for classes that read documents.'''

    @abc.abstractmethod
    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        The items returned will depend on the implementation.
        '''
        pass


class HTMLLightParserTarget(object):
    '''An HTML parser target for partial elements.

    Args:
        callback: A callback function. The function should accept the
            arguments:

                1. `tag` (str): The tag name of the element.
                2. `attrib` (dict): The attributes of the element.
                3. `text` (str, None): The text of the element.

        text_elements: A frozenset of element tag names that we should keep
            track of text.
    '''
    def __init__(self, callback,
    text_elements=frozenset(['style', 'script', 'link', 'url', 'icon'])):
        self.callback = callback
        self.text_elements = text_elements
        self.tag = None
        self.attrib = None
        self.buffer = None

    def start(self, tag, attrib):
        if tag not in self.text_elements:
            self.callback(tag, attrib, None)
            return

        if self.buffer:
            self.callback(self.tag, self.attrib, self.buffer.getvalue())

        self.tag = tag
        self.attrib = attrib
        self.buffer = io.StringIO()

    def data(self, data):
        if self.buffer:
            self.buffer.write(data)

    def end(self, tag):
        if self.buffer:
            self.callback(self.tag, self.attrib, self.buffer.getvalue())
            self.buffer = None

    def close(self):
        if self.buffer:
            self.callback(self.tag, self.attrib, self.buffer.getvalue())

        return True


COMMENT = object()
'''Comment element'''


class HTMLParserTarget(object):
    '''An HTML parser target.

    Args:
        callback: A callback function. The function should accept the
            arguments:

                1. `tag` (str): The tag name of the element.
                2. `attrib` (dict): The attributes of the element.
                3. `text` (str, None): The text of the element.
                4. `tail` (str, None): The text after the element.
                5. `end` (bool): Whether the tag is and end tag.
    '''
    def __init__(self, callback):
        self.callback = callback
        self.tag = None
        self.attrib = None
        self.buffer = None
        self.tail_buffer = None

    def start(self, tag, attrib):
        if self.buffer:
            self.callback(
                self.tag, self.attrib,
                self.buffer.getvalue(),
                None
            )
            self.buffer = None

        if self.tail_buffer:
            self.callback(
                self.tag, None,
                None,
                self.tail_buffer.getvalue(),
                True
            )
            self.tail_buffer = None

        self.tag = tag
        self.attrib = attrib
        self.buffer = io.StringIO()

    def data(self, data):
        if self.buffer:
            self.buffer.write(data)

        if self.tail_buffer:
            self.tail_buffer.write(data)

    def end(self, tag):
        if self.buffer:
            self.callback(
                tag, self.attrib,
                self.buffer.getvalue(),
                None
            )
            self.buffer = None

        if self.tail_buffer:
            self.callback(
                self.tag, None,
                None,
                self.tail_buffer.getvalue(),
                True
            )
            self.tail_buffer = None

        self.tail_buffer = io.StringIO()
        self.tag = tag

    def comment(self, text):
        self.callback(COMMENT, None, text, None)

    def close(self):
        if self.buffer:
            self.callback(
                self.tag, self.attrib,
                self.buffer.getvalue(),
                None
            )
            self.buffer = None

        if self.tail_buffer:
            self.callback(
                self.tag, None,
                None,
                self.tail_buffer.getvalue(),
                True
            )
            self.tail_buffer = None

        return True


class HTMLReadElement(object):
    '''Results from :meth:`HTMLReader.read_links`.

    Attributes:
        tag (str): The element tag name.
        attrib (dict): The element attributes.
        text (str, None): The element text.
        tail (str, None): The text after the element.
        end (bool): Whether the tag is an end tag.
    '''
    __slots__ = ('tag', 'attrib', 'text', 'tail', 'end')

    def __init__(self, tag, attrib, text, tail, end):
        self.tag = tag
        self.attrib = attrib
        self.text = text
        self.tail = tail
        self.end = end

    def __repr__(self):
        return 'HTMLReadElement({0}, {1}, {2}, {3}, {4})'.format(
            repr(self.tag), repr(self.attrib), repr(self.text),
            repr(self.tail), repr(self.end)
        )


class HTMLReader(BaseDocumentReader):
    '''HTML document reader.

    This reader uses lxml as the parser.
    '''
    BUFFER_SIZE = 1048576

    @classmethod
    def is_response(cls, response):
        '''Return whether the Response is likely to be HTML.'''
        if 'html' in response.fields.get('content-type', '').lower():
            return True

        if response.body:
            return cls.is_file(response.body.content_file)

    @classmethod
    def is_request(cls, request):
        '''Return whether the Request is likely to be a HTML.'''
        return cls.is_url(request.url_info)

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the URLInfo is likely to be a HTML.'''
        path = url_info.path.lower()
        if '.htm' in path or '.dhtm' in path or '.xht' in path:
            return True

    @classmethod
    def is_file(cls, file):
        '''Return whether the file is likely to be HTML.'''
        peeked_data = wpull.string.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<!doctype html' in peeked_data \
        or b'<head' in peeked_data \
        or b'<title' in peeked_data \
        or b'<html' in peeked_data \
        or b'<script' in peeked_data \
        or b'<table' in peeked_data \
        or b'<a href' in peeked_data:
            return True

    def read_tree(self, file, encoding=None, target_class=HTMLParserTarget,
    parser_type='html'):
        '''Return an iterator of elements found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.
            target_class: A class to be used for target parsing.
            parser_type (str): The type of parser to use. Accepted values:
                ``html``, ``xhtml``, ``xml``.

        Returns:
            iterable: class:`HTMLReadElement`
        '''
        if encoding:
            lxml_encoding = to_lxml_encoding(encoding) or 'latin1'
        else:
            lxml_encoding = encoding

        elements = []

        def callback_func(tag, attrib, text, tail=None, end=None):
            # NOTE: to_str is needed because on Python 2, byte strings may be
            # returned from lxml
            elements.append(HTMLReadElement(
                wpull.string.to_str(tag),
                wpull.string.to_str(dict(attrib))
                    if attrib is not None else None,
                wpull.string.to_str(text),
                wpull.string.to_str(tail),
                end
            ))

        target = target_class(callback_func)

        if parser_type == 'html':
            parser = lxml.html.HTMLParser(
                encoding=lxml_encoding, target=target
            )
        elif parser_type == 'xhtml':
            parser = lxml.html.XHTMLParser(
                encoding=lxml_encoding, target=target, recover=True
            )
        else:
            parser = lxml.etree.XMLParser(
                encoding=lxml_encoding, target=target, recover=True
            )

        if parser_type == 'html':
            # XXX: Force libxml2 to do full read in case of early "</html>"
            # See https://github.com/chfoo/wpull/issues/104
            # See https://bugzilla.gnome.org/show_bug.cgi?id=727935
            for dummy in range(3):
                parser.feed('<html>'.encode(encoding))

        while True:
            data = file.read(self.BUFFER_SIZE)

            if not data:
                break

            parser.feed(data)

            for element in elements:
                yield element

            elements = []

        parser.close()

        for element in elements:
            yield element

    def read_links(self, file, encoding=None):
        '''Return an iterator of partial elements found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        This function does not return elements to rebuild the tree, but
        rather element fragments that can be scraped for links.

        Returns:
            iterable: class:`HTMLReadElement`
        '''
        parser_type = self.detect_parser_type(file, encoding=encoding)

        if parser_type == 'xhtml':
            # Use the HTML parser because there exists XHTML soup
            parser_type = 'html'

        elements = self.read_tree(
            file, encoding=encoding, target_class=HTMLLightParserTarget,
            parser_type=parser_type
        )

        return elements

    @classmethod
    def parse_doctype(cls, file, encoding=None):
        '''Get the doctype from the document.

        Returns:
            str, None
        '''
        if encoding:
            lxml_encoding = to_lxml_encoding(encoding) or 'latin1'
        else:
            lxml_encoding = encoding

        try:
            parser = lxml.etree.XMLParser(encoding=lxml_encoding, recover=True)
            tree = lxml.etree.parse(
                io.BytesIO(wpull.util.peek_file(file)), parser=parser
            )
            if tree.getroot() is not None:
                return wpull.string.to_str(tree.docinfo.doctype)
        except lxml.etree.LxmlError:
            pass

    @classmethod
    def detect_parser_type(cls, file, encoding=None):
        '''Get the suitable parser type for the document.

        Returns:
            str
        '''
        is_xml = XMLDetector.is_file(file)
        doctype = cls.parse_doctype(file, encoding=encoding) or ''

        if not doctype and is_xml:
            return 'xml'

        if 'XHTML' in doctype:
            return 'xhtml'

        return 'html'


class CSSReader(BaseDocumentReader):
    '''Cascading Stylesheet Document Reader.'''
    URL_PATTERN = r'''url\(\s*['"]?(.*?)['"]?\s*\)'''
    IMPORT_URL_PATTERN = r'''@import\s*([^\s]+).*?;'''
    BUFFER_SIZE = 1048576
    STREAM_REWIND = 4096

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the document is likely to be CSS.'''
        if '.css' in url_info.path.lower():
            return True

    @classmethod
    def is_request(cls, request):
        '''Return whether the document is likely to be CSS.'''
        return cls.is_url(request.url_info)

    @classmethod
    def is_response(cls, response):
        '''Return whether the document is likely to be CSS.'''
        if 'css' in response.fields.get('content-type', '').lower():
            return True

        if response.body:
            # Stylesheet mistakenly served as HTML
            if 'html' in response.fields.get('content-type', '').lower() \
            and cls.is_file(response.body.content_file):
                return True

    @classmethod
    def is_file(cls, file):
        '''Return whether the file is likely CSS.'''
        peeked_data = wpull.string.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<html' in peeked_data:
            return False

        if re.search(br'@import |color:|background[a-z-]*:|font[a-z-]*:',
        peeked_data):
            return True

    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterable: str
        '''
        stream = codecs.getreader(encoding or 'latin1')(file)
        # stream = io.TextIOWrapper(file, encoding=encoding or 'latin1')
        buffer = None

        while True:
            text = stream.read(self.BUFFER_SIZE)

            if not text:
                break

            if not buffer and len(text) == self.BUFFER_SIZE:
                buffer = io.StringIO()

            if buffer:
                buffer.write(text)
                buffer.seek(0)

                text = buffer.getvalue()

            for link in itertools.chain(
                self.scrape_urls(text), self.scrape_imports(text)
            ):
                yield link

            if buffer:
                buffer.truncate()
                buffer.write(text[:-self.STREAM_REWIND])

    @classmethod
    def scrape_urls(cls, text):
        '''Scrape any thing that is a ``url()``.

        Returns:
            iterable: Each item is a str.
        '''
        for match in re.finditer(cls.URL_PATTERN, text):
            yield match.group(1)

    @classmethod
    def scrape_imports(cls, text):
        '''Scrape any thing that looks like an import.

        Returns:
            iterable: Each item is a str.
        '''
        for match in re.finditer(cls.IMPORT_URL_PATTERN, text):
            url_str_fragment = match.group(1)
            if url_str_fragment.startswith('url('):
                for url in cls.scrape_urls(url_str_fragment):
                    yield url
            else:
                yield url_str_fragment.strip('"\'')


class JavaScriptReader(BaseDocumentReader):
    '''JavaScript Document Reader.'''
    # Pattern based from https://github.com/internetarchive/heritrix3/
    # blob/ffd248f7800dbd4bff1cf8afaa57a0a3e945ed85/modules/src/
    # main/java/org/archive/modules/extractor/ExtractorJS.java
    URL_PATTERN = r'''(\\{0,8}['"])(https?://[^'"]{1,500}|[^\s'"]{1,500})(?:\1)'''
    BUFFER_SIZE = 1048576
    STREAM_REWIND = 4096

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the document is likely to be JS.'''
        if '.js' in url_info.path.lower():
            return True

    @classmethod
    def is_request(cls, request):
        '''Return whether the document is likely to be JS.'''
        return cls.is_url(request.url_info)

    @classmethod
    def is_response(cls, response):
        '''Return whether the document is likely to be JS.'''
        if 'javascript' in response.fields.get('content-type', '').lower():
            return True

    @classmethod
    def is_file(cls, file):
        '''Return whether the file is likely JS.'''
        peeked_data = wpull.string.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<html' in peeked_data:
            return False

        if re.search(br'var|function|setTimeout|jQuery\(',
        peeked_data):
            return True

    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterable: str
        '''
        stream = codecs.getreader(encoding or 'latin1')(file)
        # stream = io.TextIOWrapper(file, encoding=encoding or 'latin1')
        buffer = None

        while True:
            text = stream.read(self.BUFFER_SIZE)

            if not text:
                break

            if not buffer and len(text) == self.BUFFER_SIZE:
                buffer = io.StringIO()

            if buffer:
                buffer.write(text)
                buffer.seek(0)

                text = buffer.getvalue()

            for link in self.scrape_links(text):
                yield link

            if buffer:
                buffer.truncate()
                buffer.write(text[:-self.STREAM_REWIND])

    @classmethod
    def scrape_links(cls, text):
        '''Scrape any thing that might be a link.

        Returns:
            iterable: Each item is a str.
        '''
        text = re.sub(r'''(["'])([,;+])''', r'\1\2\n', text)

        for match in re.finditer(cls.URL_PATTERN, text):
            text = match.group(2)

            if wpull.url.is_likely_link(text) \
            and not wpull.url.is_unlikely_link(text):
                try:
                    yield json.loads('"{0}"'.format(text))
                except ValueError:
                    yield text


class XMLDetector(BaseDocumentDetector):
    @classmethod
    def is_file(cls, file):
        peeked_data = wpull.string.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<?xml' in peeked_data:
            return True

    @classmethod
    def is_request(cls, request):
        return cls.is_url(request.url_info)

    @classmethod
    def is_response(cls, response):
        if 'xml' in response.fields.get('content-type', '').lower():
            return True

        if response.body:
            if cls.is_file(response.body.content_file):
                return True

    @classmethod
    def is_url(cls, url_info):
        path = url_info.path.lower()
        if path.endswith('.xml'):
            return True


class SitemapParserTarget(object):
    '''An XML parser target for sitemaps.

    Args:
        link_callback: A callback function. The first argument is a str with
            the link.
    '''
    def __init__(self, link_callback):
        self.link_callback = link_callback
        self.buffer = None

    def start(self, tag, attrib):
        if tag.endswith('loc'):
            self.buffer = io.StringIO()

    def data(self, data):
        if self.buffer:
            self.buffer.write(data)

    def end(self, tag):
        if self.buffer:
            self.link_callback(self.buffer.getvalue())
            self.buffer = None

    def close(self):
        if self.buffer:
            self.link_callback(self.buffer.getvalue())

        return True


class SitemapReader(BaseDocumentReader):
    '''Sitemap XML reader.'''
    BUFFER_SIZE = 1048576
    MAX_ROBOTS_FILE_SIZE = 4096

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the document is likely to be a Sitemap.'''
        path = url_info.path.lower()
        if path == '/robots.txt':
            return True
        if 'sitemap' in path and '.xml' in path:
            return True

    @classmethod
    def is_request(cls, request):
        '''Return whether the document is likely to be a Sitemap.'''
        return cls.is_url(request.url_info)

    @classmethod
    def is_response(cls, response):
        '''Return whether the document is likely to be a Sitemap.'''
        if response.body:
            if cls.is_file(response.body.content_file):
                return True

    @classmethod
    def is_file(cls, file):
        '''Return whether the file is likely a Sitemap.'''
        peeked_data = wpull.util.peek_file(file)

        if is_gzip(peeked_data):
            try:
                peeked_data = wpull.decompression.gzip_uncompress(
                    peeked_data, truncated=True
                )
            except zlib.error:
                pass

        peeked_data = wpull.string.printable_bytes(peeked_data)

        if b'<?xml' in peeked_data \
        and (b'<sitemapindex' in peeked_data or b'<urlset' in peeked_data):
            return True

    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterable: str
        '''
        peeked_data = wpull.util.peek_file(file)

        if wpull.document.is_gzip(peeked_data):
            file = gzip.GzipFile(mode='rb', fileobj=file)

        if self.is_file(file):
            if encoding:
                lxml_encoding = to_lxml_encoding(encoding) or 'latin1'
            else:
                lxml_encoding = encoding

            links = set()

            target = SitemapParserTarget(links.add)
            parser = lxml.etree.XMLParser(
                encoding=lxml_encoding, target=target
            )

            while True:
                data = file.read(self.BUFFER_SIZE)

                if not data:
                    break

                parser.feed(data)

                for link in links:
                    yield link

                links.clear()

            parser.close()

            for link in links:
                yield link
        else:
            parser = robotexclusionrulesparser.RobotExclusionRulesParser()
            parser.parse(file.read(self.MAX_ROBOTS_FILE_SIZE))

            for link in parser.sitemaps:
                yield link


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
        return wpull.string.normalize_codec_name(encoding)
    else:
        return None


def detect_response_encoding(response, is_html=False, peek=131072):
    '''Return the likely encoding of the response document.

    Args:
        response (Response): An instance of :class:`.http.Response`.
        is_html (bool): See :func:`.util.detect_encoding`.
        peek (int): The maximum number of bytes of the document to be analyzed.

    Returns:
        ``str``, ``None``: The codec name.
    '''
    encoding = wpull.http.util.parse_charset(
        response.fields.get('content-type', '')
    )

    encoding = wpull.string.detect_encoding(
        response.body.content_peek(peek), encoding=encoding, is_html=is_html
    )

    _logger.debug('Got encoding: {0}'.format(encoding))

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
