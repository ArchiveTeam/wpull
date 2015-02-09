# encoding=utf-8
'''Base classes for processors.'''
import abc
import gettext
import logging

import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ServerError, ProtocolError, SSLVerificationError, \
    NetworkError


_logger = logging.getLogger(__name__)
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
    @trollius.coroutine
    def process(self, url_item):
        '''Process an URL Item.

        Args:
            url_item (:class:`.item.URLItem`): The URL item.

        This function handles the logic for processing a single
        URL item.

        It must call one of :meth:`.engine.URLItem.set_status` or
        :meth:`.engine.URLItem.skip`.

        Coroutine.
        '''
        pass

    def close(self):
        '''Run any clean up actions.'''
        pass


class BaseProcessorSession(object, metaclass=abc.ABCMeta):
    '''Base class for processor sessions.'''

    def _log_error(self, request, error):
        '''Log exceptions during a fetch.'''
        _logger.error(__(
            _('Fetching ‘{url}’ encountered an error: {error}'),
            url=request.url, error=error
        ))
