import contextlib
import gettext
import logging
import tempfile
import subprocess

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.document.html import HTMLReader
from wpull.driver.process import Process


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class YoutubeDlCoprocessor(object):
    def __init__(self, youtube_dl_path, proxy_address, root_path='.',
                 user_agent=None):
        self._youtube_dl_path = youtube_dl_path
        self._proxy_address = proxy_address
        self._root_path = root_path
        self._user_agent = user_agent

    @trollius.coroutine
    def process(self, url_item, request, response, file_writer_session):
        if response.status_code != 200:
            return

        if not HTMLReader.is_supported(request=request, response=response):
            return

        session = Session(
            self._proxy_address, self._youtube_dl_path, self._root_path,
            url_item, file_writer_session, self._user_agent
        )

        url = url_item.url_info.url
        _logger.info(__(_('youtube-dl fetching ‘{url}’.'), url=url))

        with contextlib.closing(session):
            yield From(session.run())

        _logger.info(__(_('youtube-dl fetched ‘{url}’.'), url=url))


class Session(object):
    def __init__(self, proxy_address, youtube_dl_path, root_path, url_item,
                 file_writer_session, user_agent):
        self._proxy_address = proxy_address
        self._youtube_dl_path = youtube_dl_path
        self._root_path = root_path
        self._url_item = url_item
        self._file_writer_session = file_writer_session
        self._user_agent = user_agent
        self._temp_dir = None

    @trollius.coroutine
    def run(self):
        host, port = self._proxy_address
        url = self._url_item.url_info.url
        args = [
            self._youtube_dl_path,
            '--proxy', 'http://{}:{}'.format(host, port),
            '--no-continue',
            '--write-info-json',
            '--write-annotations',
            '--write-thumbnail',
            '--no-cache-dir',
            '--no-progress',
            '--all-subs',
            '--output', self._get_output_template(),
            url
        ]

        if self._user_agent:
            args.extend(['--user-agent', self._user_agent])

        youtube_dl_process = Process(
            args,
            stderr_callback=self._stderr_callback,
            stdout_callback=self._stdout_callback,
        )

        yield From(youtube_dl_process.start())
        yield From(youtube_dl_process.process.wait())

    def close(self):
        if self._temp_dir:
            self._temp_dir.cleanup()

    def _get_output_template(self):
        path = self._file_writer_session.extra_resource_path('.youtube-dl')

        if not path:
            self._temp_dir = tempfile.TemporaryDirectory(
                dir=self._root_path, prefix='wpull-youtubedl'
            )
            path = '{}/tmp'.format(self._temp_dir.name)

        return '{}.%(id)s.%(format_id)s.%(ext)s'.format(path)

    def _stderr_callback(self, line):
        _logger.warning(line.decode('utf-8', 'replace').rstrip())

    def _stdout_callback(self, line):
        _logger.info(line.decode('utf-8', 'replace').rstrip())


def get_version(exe_path='youtube-dl'):
    '''Get the version string of youtube-dl.'''
    process = subprocess.Popen(
        [exe_path, '--version'],
        stdout=subprocess.PIPE
    )
    version_string = process.communicate()[0]
    return version_string.decode().strip()
