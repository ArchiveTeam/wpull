# encoding=utf-8
# Wpull. Copyright 2013-2014: Christopher Foo. License: GPL v3.
import abc
import email.utils
import logging
import os
import shutil
import sys
import time
import urllib.parse

import wpull.util


_logger = logging.getLogger(__name__)


class BaseWriter(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def rewrite_request(self, request):
        pass

    @abc.abstractmethod
    def write_response(self, request, response):
        pass


class FileWriter(BaseWriter):
    def __init__(self, path_namer, document_converter=None, headers=False,
    timestamps=True):
        self._path_namer = path_namer
        self._document_converter = document_converter
        self._headers = headers
        self._timestamps = timestamps

    def rewrite_request(self, request):
        # TODO: consult path namer and use ranges for continuing files
        pass

    def write_response(self, request, response):
        filename = self._path_namer.get_filename(request, response)

        _logger.debug('Saving file to {0}.'.format(filename))

        dir_path = os.path.dirname(filename)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)

        with wpull.util.reset_file_offset(response.body.content_file):
            with open(filename, 'wb') as out_file:
                if self._headers:
                    for data in response.iter_header_bytes():
                        out_file.write(data)
                shutil.copyfileobj(response.body.content_file, out_file)

        if self._timestamps:
            self._set_timestamp(response, filename)

    def _set_timestamp(self, response, filename):
        last_modified = response.fields.get('Last-Modified')

        if not last_modified:
            return

        try:
            last_modified = email.utils.parsedate(last_modified)
        except ValueError:
            _logger.exception('Failed to parse date.')
            return

        last_modified = time.mktime(last_modified)

        os.utime(filename, times=(time.time(), last_modified))


class NullWriter(BaseWriter):
    def rewrite_request(self, request):
        pass

    def write_response(self, request, response):
        pass


class BasePathNamer(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_filename(self, request, response):
        pass


class PathNamer(BasePathNamer):
    def __init__(self, root, index='index.html', use_dir=False, cut=None,
    protocol=False, hostname=False):
        self._root = root
        self._index = index
        self._cut = cut
        self._protocol = protocol
        self._hostname = hostname
        self._use_dir = use_dir

    def get_filename(self, request, response):
        url = request.url_info.url
        filename = url_to_filename(url, self._index)

        if self._use_dir:
            dir_path = url_to_dir_path(url, self._protocol, self._hostname)
            filename = os.path.join(dir_path, filename)

        return filename


def url_to_filename(url, index='index.html'):
    assert isinstance(url, str)
    url_split_result = urllib.parse.urlsplit(url)

    filename = url_split_result.path.split('/')[-1]

    if not filename:
        filename = index

    filename = quote_filename(filename)

    if url_split_result.query:
        query_str = urllib.parse.urlencode(
            urllib.parse.parse_qs(
                url_split_result.query, keep_blank_values=True),
            doseq=True)

        filename = '{0}?{1}'.format(filename, query_str)

    return filename


def url_to_dir_path(url, include_protocol=False, include_hostname=False):
    assert isinstance(url, str)
    url_split_result = urllib.parse.urlsplit(url)

    parts = []

    if include_protocol:
        parts.append(url_split_result.scheme)

    if include_hostname:
        parts.append(url_split_result.hostname)

    for path_part in url_split_result.path.split('/'):
        if path_part:
            parts.append(path_part)

    sanitize_path_parts(parts)
    return os.path.join(*parts)


def sanitize_path_parts(parts):
    for i in range(len(parts)):
        part = parts[i]

        if part in ('.', os.curdir):
            parts[i] = '%2E'
        elif part in ('.', os.pardir):
            parts[i] = '%2E%2E'
        else:
            parts[i] = quote_filename(part)


def quote_filename(filename):
    if sys.version_info[0] == 2:
        # FIXME: this workaround is a bit ugly
        return urllib.parse.quote(
            urllib.parse.unquote(filename).encode('utf-8'),
        ).replace('/', '%2F').decode('utf-8')
    else:
        return urllib.parse.quote(urllib.parse.unquote(filename), safe='')
