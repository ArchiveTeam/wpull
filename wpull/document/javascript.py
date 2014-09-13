import codecs
import json
import re

from wpull.document.base import BaseTextStreamReader, \
    BaseDocumentDetector
import wpull.string
from wpull.regexstream import RegexStream
import io


class JavaScriptReader(BaseDocumentDetector, BaseTextStreamReader):
    '''JavaScript Document Reader.'''
    # Pattern based from https://github.com/internetarchive/heritrix3/
    # blob/ffd248f7800dbd4bff1cf8afaa57a0a3e945ed85/modules/src/
    # main/java/org/archive/modules/extractor/ExtractorJS.java
    URL_PATTERN = r'''(\\{0,8}['"])(https?://[^'"]{1,500}|[^\s'"]{1,500})(?:\1)'''
    URL_REGEX = re.compile(URL_PATTERN)

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

    def iter_text(self, file, encoding=None):
        if isinstance(file, io.TextIOBase):
            stream = file
        else:
            stream = codecs.getreader(encoding or 'latin1')(file)
        regex_stream = RegexStream(stream, self.URL_REGEX)

        for match, text in regex_stream.stream():
            yield (text, bool(match))

    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterable: str
        '''
        return [item[0] for item in self.iter_text(file, encoding) if item[1]]
