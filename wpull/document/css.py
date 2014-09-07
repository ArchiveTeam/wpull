'''Stylesheet reader.'''
import codecs
import io
import itertools
import re

from wpull.document.base import BaseDocumentReader
import wpull.string


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
