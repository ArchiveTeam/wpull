'''Parsing using lxml and libxml2.'''
import io

import lxml.html

from wpull.collections import EmptyFrozenDict, FrozenDict
from wpull.document.htmlparse.base import BaseParser
from wpull.document.htmlparse.element import Element, Comment
from wpull.document.xml import XMLDetector
import wpull.util


class HTMLParserTarget(object):
    '''An HTML parser target.

    Args:
        callback: A callback function. The function should accept one
            argument from :mod:`.document.htmlparse.element`.
    '''
    # NOTE: If we ever support Python 2 again, byte strings may be
    # returned from lxml
    def __init__(self, callback):
        self.callback = callback
        self.tag = None
        self.attrib = None
        self.buffer = None
        self.tail_buffer = None

    def start(self, tag, attrib):
        if self.buffer:
            self.callback(Element(
                self.tag, self.attrib,
                self.buffer.getvalue(),
                None, False
            ))
            self.buffer = None

        if self.tail_buffer:
            self.callback(Element(
                self.tag, EmptyFrozenDict(),
                None,
                self.tail_buffer.getvalue(),
                True
            ))
            self.tail_buffer = None

        self.tag = tag
        self.attrib = FrozenDict(attrib)
        self.buffer = io.StringIO()

    def data(self, data):
        if self.buffer:
            self.buffer.write(data)

        if self.tail_buffer:
            self.tail_buffer.write(data)

    def end(self, tag):
        if self.buffer:
            self.callback(Element(
                tag, self.attrib,
                self.buffer.getvalue(),
                None, False
            ))
            self.buffer = None

        if self.tail_buffer:
            self.callback(Element(
                self.tag, EmptyFrozenDict(),
                None,
                self.tail_buffer.getvalue(),
                True
            ))
            self.tail_buffer = None

        self.tail_buffer = io.StringIO()
        self.tag = tag

    def comment(self, text):
        self.callback(Comment(text))

    def close(self):
        if self.buffer:
            self.callback(Element(
                self.tag, self.attrib,
                self.buffer.getvalue(),
                None, False
            ))
            self.buffer = None

        if self.tail_buffer:
            self.callback(Element(
                self.tag, EmptyFrozenDict(),
                None,
                self.tail_buffer.getvalue(),
                True
            ))
            self.tail_buffer = None

        return True


class HTMLParser(BaseParser):
    '''HTML document parser.

    This reader uses lxml as the parser.
    '''
    BUFFER_SIZE = 131072

    @property
    def parser_error(self):
        return lxml.etree.LxmlError

    def parse(self, file, encoding=None):
        parser_type = self.detect_parser_type(file, encoding=encoding)

        if parser_type == 'xhtml':
            # Use the HTML parser because there exists XHTML soup
            parser_type = 'html'

        for element in self.parse_lxml(file, encoding=encoding,
                                       parser_type=parser_type):
            yield element

    def parse_lxml(self, file, encoding=None, target_class=HTMLParserTarget,
                   parser_type='html'):
        '''Return an iterator of elements found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.
            target_class: A class to be used for target parsing.
            parser_type (str): The type of parser to use. Accepted values:
                ``html``, ``xhtml``, ``xml``.

        Returns:
            iterator: Each item is an element from
            :mod:`.document.htmlparse.element`
        '''
        if encoding:
            lxml_encoding = to_lxml_encoding(encoding) or 'latin1'
        else:
            lxml_encoding = encoding

        elements = []

        callback_func = elements.append

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

            del elements[:]

        parser.close()

        for element in elements:
            yield element

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
