'''HTML document readers.'''
import io

import lxml.etree
import lxml.html

from wpull.document.base import BaseDocumentReader
from wpull.document.util import to_lxml_encoding
from wpull.document.xml import XMLDetector
import wpull.string


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
                 text_elements=frozenset(
                     ['style', 'script', 'link', 'url', 'icon'])):
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
            return cls.is_file(response.body)

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
            # NOTE: If we ever support Python 2 again, byte strings may be
            # returned from lxml
            elements.append(HTMLReadElement(
                tag,
                dict(attrib)
                if attrib is not None else None,
                text,
                tail,
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
                return tree.docinfo.doctype
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

