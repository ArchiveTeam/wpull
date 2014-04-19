# encoding=utf-8
'''Document content post-processing.'''
import abc
import gettext
import io
import logging
import os.path
import re
import shutil

import lxml.html

from wpull.database import Status
from wpull.scraper import HTMLScraper, CSSScraper
import wpull.string
from wpull.url import URLInfo


_ = gettext.gettext
_logger = logging.getLogger(__name__)


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
    def __init__(self, url_table, backup=False):
        self._url_table = url_table
        self._backup_enabled = backup
        self._html_converter = HTMLConverter(url_table)
        self._css_converter = CSSConverter(url_table)

    def convert_all(self):
        '''Convert all links in URL table.'''
        for url_record in self._url_table.values():
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

        _logger.info(
            _('Converting links in file ‘{filename}’ (type={type}).')\
            .format(filename=filename, type=link_type)
        )

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
    def __init__(self, url_table):
        super().__init__()
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
            doctype = self.parse_doctype(in_file, encoding=encoding)
            is_xhtml = doctype and 'XHTML' in doctype

        with open(input_filename, 'rb') as in_file:
            with open(output_filename, 'wb') as bin_out_file:
                elements = self.read_tree(in_file, encoding=encoding)
                out_file = io.TextIOWrapper(bin_out_file, encoding=encoding)

                if doctype:
                    out_file.write(doctype)
                    out_file.write('\r\n')

                self._out_file = out_file
                self._encoding = encoding

                for element in elements:
                    if element.tag == wpull.document.COMMENT:
                        out_file.write(
                            '<!--{0}-->'.format(element.text)
                        )
                    elif element.end:
                        if element.tag not in lxml.html.defs.empty_tags:
                            self._out_file.write('</{0}>'.format(element.tag))

                        if element.tail:
                            self._out_file.write(element.tail)
                    else:
                        self._convert_element(element, is_xhtml=is_xhtml)

                self._out_file.close()
                self._out_file = None

    def _convert_element(self, element, is_xhtml=False):
        self._out_file.write('<')
        self._out_file.write(element.tag)

        new_text = element.text
        unfilled_value = object()
        new_attribs = dict(((name, unfilled_value) for name in element.attrib))

        for link_info in self.iter_links_element(element):
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

            if new_value:
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

        if is_xhtml and element.tag in lxml.html.defs.empty_tags:
            self._out_file.write('/')

        self._out_file.write('>')

        if element.tag not in lxml.html.defs.empty_tags:
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

        self._css_already_done.add(link_info.element)

        return new_text

    def _get_new_url(self, url_info):
        url_record = self._url_table.get(url_info.url)

        if url_record \
        and url_record.status == Status.done and url_record.filename:
            new_url = url_record.filename
        else:
            new_url = url_info.url

        return new_url


class CSSConverter(CSSScraper, BaseDocumentConverter):
    '''CSS converter.'''
    ALL_URL_PATTERN = r'{0}|{1}'.format(
        CSSScraper.URL_PATTERN, CSSScraper.IMPORT_URL_PATTERN)

    def __init__(self, url_table):
        super().__init__()
        self._url_table = url_table

    def convert(self, input_filename, output_filename, base_url=None):
        with open(input_filename, 'rb') as in_file:
            text = in_file.read()

        encoding = wpull.string.detect_encoding(text)
        text = text.decode(encoding)
        new_text = self.convert_text(text, base_url)

        with open(output_filename, 'wb') as out_file:
            out_file.write(new_text.encode(encoding))

    def convert_text(self, text, base_url=None):
        def repl(match):
            url = match.group(1) or match.group(2)

            if base_url:
                url = wpull.url.urljoin(base_url, url)

            url_record = self._url_table.get(url)

            if url_record \
            and url_record.status == Status.done and url_record.filename:
                new_url = url_record.filename
            else:
                new_url = url

            return match.group().replace(url, new_url)

        return re.sub(self.ALL_URL_PATTERN, repl, text)
