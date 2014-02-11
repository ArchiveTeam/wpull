# encoding=utf-8
'''Document content post-processing.'''
import abc
import gettext
import logging
import os.path
import re
import shutil

from wpull.database import Status
from wpull.document import CSSReader, HTMLReader
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

    def convert_by_record(self, url_record):
        '''Convert using given URL Record.'''
        filename = self._path_namer.get_filename(
            URLInfo.parse(url_record.url)
        )

        if not os.path.exists(filename):
            return

        if url_record.link_type not in ('css', 'html'):
            return

        _logger.info(
            _('Converting links in file ‘{filename}.’')\
            .format(filename=filename)
        )

        if self._backup_enabled:
            shutil.copyfile(filename, filename + '.orig')

        if url_record.link_type == 'css':
            self._css_converter.convert(
                filename, filename, base_url=url_record.url)
        elif url_record.link_type == 'html':
            self._html_converter.convert(
                filename, filename, base_url=url_record.url)


class HTMLConverter(HTMLReader, BaseDocumentConverter):
    '''HTML converter.'''
    def convert(self, input_filename, output_filename, base_url=None):
        raise NotImplementedError()


class CSSConverter(CSSReader, BaseDocumentConverter):
    '''CSS converter.'''
    ALL_URL_PATTERN = r'{0}|{1}'.format(
        CSSReader.URL_PATTERN, CSSReader.IMPORT_URL_PATTERN)

    def __init__(self, path_namer, url_table):
        self._path_namer = path_namer
        self._url_table = url_table

    def convert(self, input_filename, output_filename, base_url=None):
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

        with open(input_filename, 'rb') as in_file:
            text = in_file.read()

        encoding = wpull.util.detect_encoding(text)
        text = text.decode(encoding)

        new_text = re.sub(self.ALL_URL_PATTERN, repl, text)

        with open(output_filename, 'wb') as out_file:
            out_file.write(new_text.encode(encoding))
