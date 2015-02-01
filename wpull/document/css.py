'''Stylesheet reader.'''
import codecs
import io
import re

from wpull.document.base import BaseDocumentDetector, BaseTextStreamReader
from wpull.regexstream import RegexStream
import wpull.string
import wpull.util


class CSSReader(BaseDocumentDetector, BaseTextStreamReader):
    '''Cascading Stylesheet Document Reader.'''
    URL_PATTERN = r'''url\(\s*(['"]?)(.{1,500}?)(?:\1)\s*\)'''
    IMPORT_URL_PATTERN = r'''@import\s*(?:url\()?['"]?([^\s'")]{1,500}).*?;'''
    URL_REGEX = re.compile(r'{}|{}'.format(URL_PATTERN, IMPORT_URL_PATTERN))
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
               and cls.is_file(response.body):
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

    def iter_text(self, file, encoding=None):
        if isinstance(file, io.TextIOBase):
            stream = file
        else:
            stream = codecs.getreader(encoding or 'latin1')(file)

        regex_stream = RegexStream(stream, self.URL_REGEX)

        for match, text in regex_stream.stream():
            if match:
                yield (text, 'import' if match.group(3) else 'url')
            else:
                yield (text, False)
