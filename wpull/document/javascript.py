import codecs
import io
import json
import re

from wpull.document.base import BaseDocumentReader
import wpull.string


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
