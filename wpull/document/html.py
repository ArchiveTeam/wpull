'''HTML document readers.'''
import io

from wpull.document.base import BaseHTMLReader, BaseDocumentDetector
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


class HTMLReader(BaseDocumentDetector, BaseHTMLReader):
    '''HTML document reader.

    Arguments:
        html_parser (:class:`.document.htmlparse.BaseParser`): An HTML parser.
    '''
    def __init__(self, html_parser):
        self._html_parser = html_parser

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

    def iter_elements(self, file, encoding=None):
        return self._html_parser.parse(file, encoding)
