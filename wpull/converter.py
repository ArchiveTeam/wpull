# encoding=utf-8
'''Document content post-processing.'''
import abc
import gettext
import logging
import os.path
import re
import shutil

from wpull.database import Status
from wpull.scraper import HTMLScraper, CSSScraper
from wpull.url import URLInfo
import wpull.util


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
        path_namer: An instance of :class:`.writer.PathNamer`.
        url_table: An instance of :class:`.database.URLTable`.
        backup (bool): Whether back up files are created.
    '''
    def __init__(self, path_namer, url_table, backup=False):
        self._path_namer = path_namer
        self._url_table = url_table
        self._backup_enabled = backup
        self._html_converter = HTMLConverter(path_namer, url_table)
        self._css_converter = CSSConverter(path_namer, url_table)

    def convert_all(self):
        '''Convert all links in URL table.'''
        for url_record in self._url_table.values():
            if url_record.status != Status.done:
                continue

            self.convert_by_record(url_record)

    def convert_by_record(self, url_record):
        '''Convert using given URL Record.'''
        filename = self._path_namer.get_filename(
            URLInfo.parse(url_record.url)
        )

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
                in_file, url_info=url_record.url_info):
                    link_type = 'html'
                elif CSSScraper.is_supported(
                in_file, url_info=url_record.url_info):
                    link_type = 'css'
                else:
                    link_type = None

        _logger.info(
            _('Converting links in file ‘{filename}’ (type={type}).')\
            .format(filename=filename, type=link_type)
        )

        if self._backup_enabled:
            shutil.copy2(filename, filename + '.orig')

        if link_type == 'css':
            self._css_converter.convert(
                filename, filename, base_url=url_record.url)
        elif link_type == 'html':
            self._html_converter.convert(
                filename, filename, base_url=url_record.url)


class HTMLConverter(HTMLScraper, BaseDocumentConverter):
    '''HTML converter.'''
    def __init__(self, path_namer, url_table):
        super().__init__()
        self._path_namer = path_namer
        self._url_table = url_table
        self._css_converter = CSSConverter(path_namer, url_table)

    def convert(self, input_filename, output_filename, base_url=None):
        css_already_done = set()

        with open(input_filename, 'rb') as in_file:
            tree = self.parse(in_file, base_url=base_url)

        root = tree.getroot()

        if root is None:
            _logger.warning(
                _('Failed to convert ‘{filename}’.')\
                .format(filename=input_filename)
            )
            return

        encoding = wpull.util.to_str(tree.docinfo.encoding)

        for link_info in self.iter_links(root):
            if link_info.value_type == 'plain':
                self._convert_plain(link_info, root, encoding)
            elif link_info.value_type == 'css':
                self._convert_css(link_info, css_already_done, base_url)

        tree.write(
            output_filename, method='html', pretty_print=True,
            encoding=encoding
        )

    def _convert_plain(self, link_info, root, encoding):
        base_url = wpull.util.to_str(root.base_url)

        if link_info.base_link:
            base_url = wpull.url.urljoin(base_url, link_info.base_link)

        url = wpull.url.urljoin(base_url, link_info.link)
        url_info = URLInfo.parse(url, encoding=encoding)
        new_url = self._get_new_url(url_info)

        link_info.element.set(link_info.attrib, new_url)

    def _convert_css(self, link_info, css_already_done, base_url=None):
        if link_info.attrib:
            done_key = (link_info.element, link_info.attrib)

            if done_key in css_already_done:
                return

            text = wpull.util.to_str(link_info.element.get(link_info.attrib))
            new_text = self._css_converter.convert_text(text, base_url)

            link_info.element.set(link_info.attrib, new_text)
            css_already_done.add(done_key)
        else:
            if link_info.element in css_already_done:
                return

            text = wpull.util.to_str(link_info.element.text)
            new_text = self._css_converter.convert_text(text, base_url)
            link_info.element.text = new_text

            css_already_done.add(link_info.element)

    def _get_new_url(self, url_info):
        if url_info.url in self._url_table \
        and self._url_table[url_info.url].status == Status.done:
            new_url = self._path_namer.get_filename(url_info)
        else:
            new_url = url_info.url

        return new_url


class CSSConverter(CSSScraper, BaseDocumentConverter):
    '''CSS converter.'''
    ALL_URL_PATTERN = r'{0}|{1}'.format(
        CSSScraper.URL_PATTERN, CSSScraper.IMPORT_URL_PATTERN)

    def __init__(self, path_namer, url_table):
        super().__init__()
        self._path_namer = path_namer
        self._url_table = url_table

    def convert(self, input_filename, output_filename, base_url=None):
        with open(input_filename, 'rb') as in_file:
            text = in_file.read()

        encoding = wpull.util.detect_encoding(text)
        text = text.decode(encoding)
        new_text = self.convert_text(text, base_url)

        with open(output_filename, 'wb') as out_file:
            out_file.write(new_text.encode(encoding))

    def convert_text(self, text, base_url=None):
        def repl(match):
            url = match.group(1) or match.group(2)

            if base_url:
                url = wpull.url.urljoin(base_url, url)

            if url in self._url_table \
            and self._url_table[url].status == Status.done:
                new_url = self._path_namer.get_filename(URLInfo.parse(url))
            else:
                new_url = url

            return match.group().replace(url, new_url)

        return re.sub(self.ALL_URL_PATTERN, repl, text)
