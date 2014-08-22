# encoding=utf-8
'''Base classes for processors.'''
import abc

import trollius


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
