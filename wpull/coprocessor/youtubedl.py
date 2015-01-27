import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.driver.process import Process


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class YoutubeDlCoprocessor(object):
    def __init__(self, youtube_dl_path, proxy_address):
        self._youtube_dl_path = youtube_dl_path
        self._proxy_address = proxy_address

    @trollius.coroutine
    def process(self, url_item, request, response, file_writer_session):
        host, port = self._proxy_address
        url = url_item.url_info.url
        youtube_dl_process = Process([
            self._youtube_dl_path,
            '--proxy', 'http://{}:{}'.format(host, port),
            url
        ])

        _logger.info(__(
            _('youtube-dl fetching ‘{url}’.'),
            url=url
        ))

        yield From(youtube_dl_process.start())
        yield From(youtube_dl_process.process.wait())

        _logger.info(__(
            _('youtube-dl fetched ‘{url}’.'),
            url=url
        ))
