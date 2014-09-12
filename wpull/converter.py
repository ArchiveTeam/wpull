# encoding=utf-8
'''Document content post-processing.'''
import abc
import codecs
import gettext
import io
import logging
import os.path
import shutil

from wpull.backport.logging import BraceMessage as __
from wpull.database.base import NotFound
from wpull.document.htmlparse.element import Comment, Element, Doctype
from wpull.item import Status
from wpull.scraper.css import CSSScraper
from wpull.scraper.html import HTMLScraper, ElementWalker
from wpull.url import URLInfo
import wpull.string


_ = gettext.gettext
_logger = logging.getLogger(__name__)


# Snipped from lxml.html.def:
empty_tags = frozenset([
    'area', 'base', 'basefont', 'br', 'col', 'frame', 'hr',
    'img', 'input', 'isindex', 'link', 'meta', 'param'])


class BaseDocumentConverter(object, metaclass=abc.ABCMeta):
    '''Base class for classes that convert links within a document.'''
    @abc.abstractmethod
    def convert(self, input_filename, output_filename, base_url=None):
        pass


class BatchDocumentConverter(object):
    '''Convert all documents in URL table.

    Args:
        url_table: An instance of :class:`.database.URLTable`.
        backup (bool): Whether back up files are created.
    '''
    def __init__(self, html_parser, element_walker, url_table, backup=False):
        self._url_table = url_table
        self._backup_enabled = backup
        self._html_converter = HTMLConverter(html_parser, element_walker,
                                             url_table)
        self._css_converter = CSSConverter(url_table)

    def convert_all(self):
        '''Convert all links in URL table.'''
        for url_record in self._url_table.get_all():
            if url_record.status != Status.done:
                continue

            self.convert_by_record(url_record)

    def convert_by_record(self, url_record):
        '''Convert using given URL Record.'''
        filename = url_record.filename

        if not os.path.exists(filename):
            return

        if url_record.link_type:
            if url_record.link_type not in ('css', 'html'):
                return
            else:
                link_type = url_record.link_type
        else:
            with open(filename, 'rb') as in_file:
                if HTMLScraper.is_supported(
                        file=in_file, url_info=url_record.url_info):
                    link_type = 'html'
                elif CSSScraper.is_supported(
                        file=in_file, url_info=url_record.url_info):
                    link_type = 'css'
                else:
                    link_type = None

        _logger.info(__(
            _('Converting links in file ‘{filename}’ (type={type}).'),
            filename=filename, type=link_type
        ))

        if self._backup_enabled:
            shutil.copy2(filename, filename + '.orig')

        temp_filename = filename + '-new'

        if link_type == 'css':
            self._css_converter.convert(
                filename, temp_filename, base_url=url_record.url)
        elif link_type == 'html':
            self._html_converter.convert(
                filename, temp_filename, base_url=url_record.url)
        else:
            raise Exception('Unknown link type.')

        os.remove(filename)
        os.rename(temp_filename, filename)


class HTMLConverter(HTMLScraper, BaseDocumentConverter):
    '''HTML converter.'''
    def __init__(self, html_parser, element_walker, url_table):
        super().__init__(html_parser, element_walker)
        self._url_table = url_table
        self._css_converter = CSSConverter(url_table)
        self._out_file = None
        self._css_already_done = None
        self._base_url = None
        self._encoding = None

    def convert(self, input_filename, output_filename, base_url=None):
        self._css_already_done = set()
        self._base_url = base_url

        with open(input_filename, 'rb') as in_file:
            encoding = wpull.string.detect_encoding(
                in_file.peek(1048576), is_html=True
            )

        with open(input_filename, 'rb') as in_file:
            try:
                doctype = self._html_parser.parse_doctype(in_file,
                                                          encoding=encoding)
                is_xhtml = doctype and 'XHTML' in doctype
            except AttributeError:
                # using html5lib
                is_xhtml = False
                doctype = None

        with open(input_filename, 'rb') as in_file:
            with open(output_filename, 'wb') as bin_out_file:
                elements = self.iter_elements(in_file, encoding=encoding)
                out_file = io.TextIOWrapper(bin_out_file, encoding=encoding)

                if doctype:
                    out_file.write(doctype)
                    out_file.write('\r\n')

                self._out_file = out_file
                self._encoding = encoding

                for element in elements:
                    if isinstance(element, Comment):
                        out_file.write(
                            '<!--{0}-->'.format(element.text)
                        )
                    elif isinstance(element, Element):
                        if element.end:
                            if element.tag not in empty_tags:
                                self._out_file.write('</{0}>'
                                                     .format(element.tag))

                            if element.tail:
                                self._out_file.write(element.tail)
                        else:
                            self._convert_element(element, is_xhtml=is_xhtml)
                    elif isinstance(element, Doctype):
                        doctype = element.text
                        is_xhtml = doctype and 'XHTML' in doctype

                self._out_file.close()
                self._out_file = None

    def _convert_element(self, element, is_xhtml=False):
        self._out_file.write('<')
        self._out_file.write(element.tag)

        new_text = element.text
        unfilled_value = object()
        new_attribs = dict(((name, unfilled_value) for name in element.attrib))

        for link_info in self._element_walker.iter_links_element(element):
            new_value = None

            if link_info.value_type == 'plain':
                new_value = self._convert_plain(link_info)
            elif link_info.value_type == 'css':
                if link_info.attrib:
                    new_value = self._convert_css_attrib(link_info)
                else:
                    text = self._convert_css_text(link_info)

                    if text:
                        new_text = text

            if new_value and link_info.attrib:
                if new_attribs[link_info.attrib] == unfilled_value:
                    new_attribs[link_info.attrib] = [new_value]
                else:
                    new_attribs[link_info.attrib].append(new_value)

        for name in new_attribs:
            if new_attribs[name] == unfilled_value:
                value = element.attrib[name]
            else:
                value = ' '.join(new_attribs[name])

            self._out_file.write(' {0}="{1}"'.format(name, value))

        if is_xhtml and element.tag in empty_tags:
            self._out_file.write('/')

        self._out_file.write('>')

        if element.tag not in empty_tags:
            if new_text:
                self._out_file.write(new_text)

    def _convert_plain(self, link_info):
        base_url = self._base_url

        if link_info.base_link:
            if self._base_url:
                base_url = wpull.url.urljoin(
                    self._base_url, link_info.base_link
                )
            else:
                base_url = link_info.base_link

        if base_url:
            url = wpull.url.urljoin(base_url, link_info.link)
        else:
            url = link_info.link

        url_info = URLInfo.parse(url, encoding=self._encoding)
        new_url = self._get_new_url(url_info)

        return new_url

    def _convert_css_attrib(self, link_info):
        done_key = (link_info.element, link_info.attrib)

        if done_key in self._css_already_done:
            return

        text = wpull.string.to_str(
            link_info.element.attrib.get(link_info.attrib)
        )
        new_value = self._css_converter.convert_text(
            text, base_url=self._base_url
        )

        self._css_already_done.add(done_key)

        return new_value

    def _convert_css_text(self, link_info):
        if link_info.element in self._css_already_done:
            return

        text = wpull.string.to_str(link_info.element.text)
        new_text = self._css_converter.convert_text(
            text, base_url=self._base_url
        )

        self._css_already_done.add(id(link_info.element))

        return new_text

    def _get_new_url(self, url_info):
        try:
            url_record = self._url_table.get_one(url_info.url)
        except NotFound:
            url_record = None

        if url_record \
           and url_record.status == Status.done and url_record.filename:
            new_url = url_record.filename
        else:
            new_url = url_info.url

        return new_url


class CSSConverter(CSSScraper, BaseDocumentConverter):
    '''CSS converter.'''
    def __init__(self, url_table):
        super().__init__()
        self._url_table = url_table

    def convert(self, input_filename, output_filename, base_url=None):
        with open(input_filename, 'rb') as in_file, \
                open(output_filename, 'wb') as out_file:
            encoding = wpull.string.detect_encoding(
                wpull.util.peek_file(in_file))
            out_stream = codecs.getwriter(encoding)(out_file)

            for text, is_link in self.iter_processed_text(in_file, encoding):
                if is_link:
                    out_stream.write(self.get_new_url(text, base_url))
                else:
                    out_stream.write(text)

    def convert_text(self, text, base_url=None):
        text_list = []
        for text, is_link in self.iter_processed_text(io.StringIO(text)):
            if is_link:
                text_list.append(self.get_new_url(text, base_url))
            else:
                text_list.append(text)

        return ''.join(text_list)

    def get_new_url(self, url, base_url=None):
        if base_url:
            url = wpull.url.urljoin(base_url, url)

        url_record = self._url_table.get_one(url)

        if url_record \
           and url_record.status == Status.done and url_record.filename:
            new_url = url_record.filename
        else:
            new_url = url

        return new_url


# TODO: add javascript conversion
