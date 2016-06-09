'''Delegation to other processor.'''
import gettext
import logging


import asyncio

from wpull.backport.logging import StyleAdapter
from wpull.pipeline.session import ItemSession
from wpull.processor.base import BaseProcessor


_logger = StyleAdapter(logging.getLogger())
_ = gettext.gettext


class DelegateProcessor(BaseProcessor):
    '''Delegate to Web or FTP processor.'''
    def __init__(self):
        self._processors = {}

    @asyncio.coroutine
    def process(self, item_session: ItemSession):
        scheme = item_session.url_record.url_info.scheme

        processor = self._processors.get(scheme)

        if processor:
            return (yield from processor.process(item_session))
        else:
            _logger.warning(
                _('No processor available to handle {scheme} scheme.'),
                scheme=repr(scheme)
            )
            item_session.skip()

    def close(self):
        for processor in self._processors.values():
            processor.close()

    def register(self, scheme: str, processor: BaseProcessor):
        self._processors[scheme] = processor
