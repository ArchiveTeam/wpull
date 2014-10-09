'''FTP'''
import trollius

from wpull.processor.base import BaseProcessor


class FTPProcessor(BaseProcessor):
    def __init__(self, ftp_client):
        self._ftp_client = ftp_client

    @trollius.coroutine
    def process(self, url_item):
        with self._ftp_client.session() as session:
            # TODO: things
            pass
