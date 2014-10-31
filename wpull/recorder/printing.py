'''Printing protocol events.'''
import contextlib

from wpull.recorder.base import BaseRecorder, BaseRecorderSession


class DebugPrintRecorder(BaseRecorder):
    '''Print out all events for debugging.'''
    @contextlib.contextmanager
    def session(self):
        print('Session started')
        try:
            yield DebugPrintRecorderSession()
        finally:
            print('Session ended')


class DebugPrintRecorderSession(BaseRecorderSession):
    '''Debugging print recorder session.'''
    def pre_request(self, request):
        print(request)

    def request(self, request):
        print(request)

    def request_data(self, data):
        print(data)

    def pre_response(self, response):
        print(response)

    def response(self, response):
        print(response)

    def response_data(self, data):
        print(data)

    def begin_control(self, request):
        print(request)

    def end_control(self, response):
        print(response)

    def request_control_data(self, data):
        print(data)

    def response_control_data(self, data):
        print(data)


class PrintServerResponseRecorder(BaseRecorder):
    '''Print the server HTTP response.'''
    @contextlib.contextmanager
    def session(self):
        yield PrintServerResponseRecorderSession()


class PrintServerResponseRecorderSession(BaseRecorderSession):
    '''Print Server Response Recorder Session.'''
    def response(self, response):
        print(str(response))
