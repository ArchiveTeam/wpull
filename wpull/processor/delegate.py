'''Delegation to other processor.'''
import gettext
import logging

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.processor.base import BaseProcessor


_logger = logging.getLogger()
_ = gettext.gettext


class DelegateProcessor(BaseProcessor):
    '''Delegate to Web or FTP processor.'''
    def __init__(self, http_processor, ftp_processor):
        self.http_processor = http_processor
        self.ftp_processor = ftp_processor

    @trollius.coroutine
    def process(self, url_item):
        scheme = url_item.url_info.scheme

        if scheme in ('http', 'https'):
            raise Return((yield From(self.http_processor.process(url_item))))
        elif scheme == 'ftp':
            raise Return((yield From(self.ftp_processor.process(url_item))))
        else:
            _logger.warning(__(
                _('No processor available to handle {scheme} scheme.'),
                scheme=repr(scheme)
            ))

    def close(self):
        self.http_processor.close()
        self.ftp_processor.close()
