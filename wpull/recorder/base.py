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

    1. request_control_data: Commands sent to the server.
    2. response_controL_data: Reply received from the server.
    3. pre_request: Data connection opened.
    4. request_data (optional): Bytes of the file upload.
    5. request (optional): File uploaded.
    6. pre_response (optional): Beginning of file download.
    7. response_data (optional): Bytes of the file download.
    8. response: File downloaded. Data connection closed.
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

    def request_control_data(self, data):
        '''Callback for out-of-band bytes that was sent.'''

    def response_control_data(self, data):
        '''Callback for out-of-band bytes that was received.'''
