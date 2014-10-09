'''Base recorders.'''

import abc
import contextlib


class BaseRecorder(object, metaclass=abc.ABCMeta):
    '''Base class for recorders.

    Recorders are designed to be passed to a :class:`.http.client.Client`.
    '''
    @abc.abstractmethod
    @contextlib.contextmanager
    def session(self):
        '''Return a new session.'''

    def close(self):
        '''Perform any clean up actions.'''


class BaseRecorderSession(object, metaclass=abc.ABCMeta):
    def pre_request(self, request):
        '''Callback for when a request is about to be made.'''

    def request(self, request):
        '''Callback for when a request has been made.'''

    def request_data(self, data):
        '''Callback for the bytes that was sent.'''

    def pre_response(self, response):
        '''Callback for when the response header has been received.'''

    def response(self, response):
        '''Callback for when the response has been completely received.'''

    def response_data(self, data):
        '''Callback for the bytes that was received.'''
