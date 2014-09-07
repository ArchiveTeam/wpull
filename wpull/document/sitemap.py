'''Sitemap.xml'''
import gzip
import io
import zlib

import lxml
import lxml.etree

from wpull.document.base import BaseDocumentReader
from wpull.document.util import is_gzip, to_lxml_encoding
from wpull.thirdparty import robotexclusionrulesparser
import wpull.decompression
import wpull.util


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
            if cls.is_file(response.body):
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

        if is_gzip(peeked_data):
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
