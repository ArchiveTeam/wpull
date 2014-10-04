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
    def __init__(self, web_processor, ftp_processor):
        self.web_processor = web_processor
        self.ftp_processor = ftp_processor

    @trollius.coroutine
    def process(self, url_item):
        scheme = url_item.url_info.scheme

        if scheme in ('http', 'https'):
            raise Return((yield From(self.web_processor.process(url_item))))
        elif scheme == 'ftp':
            raise Return((yield From(self.ftp_processor.process(url_item))))
        else:
            _logger.warning(__(
                _('No processor available to handle {scheme} scheme.'),
                scheme=repr(scheme)
            ))

    def close(self):
        self.web_processor.close()
        self.ftp_processor.close()
