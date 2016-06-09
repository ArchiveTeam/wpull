# encoding=utf-8
'''Base classes for processors.'''
import abc
import gettext
import logging

import asyncio

from wpull.backport.logging import StyleAdapter
from wpull.errors import ServerError, ProtocolError, SSLVerificationError, \
    NetworkError
from wpull.pipeline.session import ItemSession

_logger = StyleAdapter(logging.getLogger(__name__))
_ = gettext.gettext


REMOTE_ERRORS = (
    ServerError,
    ProtocolError,
    SSLVerificationError,
    NetworkError,
)
'''List of error classes that are errors that occur with a server.'''


class BaseProcessor(object, metaclass=abc.ABCMeta):
    '''Base class for processors.

    Processors contain the logic for processing requests.
    '''
    @asyncio.coroutine
    def process(self, item_session: ItemSession):
        '''Process an URL Item.

        Args:
            item_session: The URL item.

        This function handles the logic for processing a single
        URL item.

        It must call one of :meth:`.engine.URLItem.set_status` or
        :meth:`.engine.URLItem.skip`.

        Coroutine.
        '''

    def close(self):
        '''Run any clean up actions.'''


class BaseProcessorSession(object, metaclass=abc.ABCMeta):
    '''Base class for processor sessions.'''

    def _log_error(self, request, error):
        '''Log exceptions during a fetch.'''
        _logger.error(
            _('Fetching ‘{url}’ encountered an error: {error}'),
            url=request.url, error=error
        )
