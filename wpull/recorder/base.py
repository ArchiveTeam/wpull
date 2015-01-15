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
    '''Base recorder session.

    The order of the callbacks depend on the protocol.

    For HTTP, the following sequence is typical:

    1. pre_request: Beginning of header.
    2. request_data: Bytes of the header and upload body.
    3. request: Finished sending the request.
    4. pre_response: Beginning of header.
    5. response_data: Bytes of the header, download body, trailers.
    6. response: End of the response.

    For FTP:

    1. begin_control: Control connection opened.
    2. request_control_data: Commands sent to the server.
    3. response_control_data: Reply received from the server.
    4. pre_request/pre_response: Data connection opened.
    5. request_data/response_data: Bytes of the file upload/download.
    6. request/response: File uploaded/downloaded. Data connection closed.
    7. end_control: Control connection closed.
    '''

    def pre_request(self, request):
        '''Callback for when a request is about to be made.'''

    def request(self, request):
        '''Callback for when a request has been made.'''

    def request_data(self, data):
        '''Callback for the in-band bytes that was sent.'''

    def pre_response(self, response):
        '''Callback for when the response header has been received.'''

    def response(self, response):
        '''Callback for when the response has been completely received.'''

    def response_data(self, data):
        '''Callback for the in-band bytes that was received.'''

    def begin_control(self, request):
        '''Callback for beginning of a control session.'''

    def request_control_data(self, data):
        '''Callback for out-of-band bytes that was sent.'''

    def response_control_data(self, data):
        '''Callback for out-of-band bytes that was received.'''

    def end_control(self, response):
        '''Callback for ending of a control session.'''
