# encoding=utf-8
# Wpull. Copyright 2013-2014: Christopher Foo. License: GPL v3.
import abc
import email.utils
import gettext
import http.client
import itertools
import logging
import os
import shutil
import sys
import time
import urllib.parse

import wpull.util


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class BaseWriter(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def session(self):
        pass


class BaseWriterSession(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def process_request(self, request):
        pass

    @abc.abstractmethod
    def process_response(self, response):
        pass

    @abc.abstractmethod
    def save_document(self, response):
        pass

    @abc.abstractmethod
    def discard_document(self, response):
        pass


class BaseFileWriter(BaseWriter):
    def __init__(self, path_namer, file_continuing=False,
    headers_included=False, local_timestamping=True):
        self._path_namer = path_namer
        self._file_continuing = file_continuing
        self._headers_included = headers_included
        self._local_timestamping = local_timestamping

    @abc.abstractproperty
    def session_class(self):
        pass

    def session(self):
        return self.session_class(
            self._path_namer,
            self._file_continuing,
            self._headers_included,
            self._local_timestamping,
        )


class BaseFileWriterSession(BaseWriterSession):
    def __init__(self, path_namer, file_continuing,
    headers_included, local_timestamping):
        self._path_namer = path_namer
        self._file_continuing = file_continuing
        self._headers_included = headers_included
        self._local_timestamping = local_timestamping
        self._filename = None

    @classmethod
    def open_file(cls, filename, response, mode='wb+'):
        _logger.debug('Saving file to {0}, mode={1}.'.format(
            filename, mode))

        dir_path = os.path.dirname(filename)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path)

        response.body.content_file = open(filename, mode)

    @classmethod
    def set_timestamp(cls, filename, response):
        last_modified = response.fields.get('Last-Modified')

        if not last_modified:
            return

        try:
            last_modified = email.utils.parsedate(last_modified)
        except ValueError:
            _logger.exception('Failed to parse date.')
            return

        last_modified = time.mktime(last_modified)

        os.utime(filename, (time.time(), last_modified))

    @classmethod
    def save_headers(cls, filename, response):
        new_filename = filename + '-new'

        with open('wb') as new_file:
            new_file.write(response.header())

            with wpull.util.reset_file_offset(response.body.content_file):
                response.body.content_file.seek(0)
                shutil.copyfileobj(response.body.content_file, new_file)

        os.remove(filename)
        os.rename(new_filename, filename)

    def process_request(self, request):
        if not self._filename:
            self._filename = self._compute_filename(request)

            if self._file_continuing and self._filename:
                self._process_file_continue_request(request)

        return request

    def _compute_filename(self, request):
        return self._path_namer.get_filename(request.url_info)

    def _process_file_continue_request(self, request):
        if os.path.exists(self._filename):
            size = os.path.getsize(self._filename)
            request.fields['Range'] = 'bytes={0}-'.format(size)

            _logger.debug('Continue file from {0}.'.format(size))
        else:
            _logger.debug('No file to continue.')

    def process_response(self, response):
        if not self._filename:
            return

        code = response.status_code

        if self._file_continuing:
            self._process_file_continue_response(response)
        elif code == http.client.OK:
            self.open_file(self._filename, response)

    def _process_file_continue_response(self, response):
        code = response.status_code

        if code == http.client.PARTIAL_CONTENT:
            self.open_file(self._filename, response, mode='ab+')
        else:
            raise IOError(
                _('Could not continue file download: {filename}.')\
                    .format(filename=self._filename))

    def save_document(self, response):
        if self._filename and os.path.exists(self._filename):
            if self._headers_included:
                self.save_headers(self._filename, response)

            if self._local_timestamping:
                self.set_timestamp(self._filename, response)

    def discard_document(self, response):
        if self._filename and os.path.exists(self._filename):
            os.remove(self._filename)


class OverwriteFileWriter(BaseFileWriter):
    @property
    def session_class(self):
        return OverwriteFileWriterSession


class OverwriteFileWriterSession(BaseFileWriterSession):
    pass


class IgnoreFileWriter(BaseFileWriter):
    @property
    def session_class(self):
        return IgnoreFileWriterSession


class IgnoreFileWriterSession(BaseFileWriterSession):
    def process_request(self, request):
        if not self._filename or not os.path.exists(self._filename):
            return super().process_request(request)


class AntiClobberFileWriter(BaseFileWriter):
    @property
    def session_class(self):
        return AntiClobberFileWriterSession


class AntiClobberFileWriterSession(BaseFileWriterSession):
    def _compute_filename(self, request):
        original_filename = self._path_namer.get_filename(request.url_info)
        candidate_filename = original_filename

        for suffix in itertools.count():
            if suffix:
                candidate_filename = '{0}.{1}'.format(original_filename,
                    suffix)

            if not os.path.exists(candidate_filename):
                return candidate_filename


class TimestampingFileWriter(BaseFileWriter):
    @property
    def session_class(self):
        return TimestampingFileWriterSession


class TimestampingFileWriterSession(BaseFileWriterSession):
    def process_request(self, request):
        request = super().request(request)

        date_str = email.utils.formatdate(os.path.getmtime(self._filename))
        request.fields['If-Modified-Since'] = date_str

        return request


class NullWriter(BaseWriter):
    def session(self):
        return NullWriterSession()


class NullWriterSession(BaseWriterSession):
    def process_request(self, request):
        return request

    def process_response(self, response):
        return response

    def discard_document(self, response):
        pass

    def save_document(self, response):
        pass


class BasePathNamer(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_filename(self, url_info):
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

    def get_filename(self, url_info):
        url = url_info.url
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
