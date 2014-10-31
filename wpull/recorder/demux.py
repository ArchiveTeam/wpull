'''Using multiple recorders as a single recorder.'''

import contextlib

from wpull.recorder.base import BaseRecorder, BaseRecorderSession


class DemuxRecorder(BaseRecorder):
    '''Put multiple recorders into one.

    Args:
        recorders (list): List of recorder instances.
    '''
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders

    @contextlib.contextmanager
    def session(self):
        dmux = DemuxRecorderSession(self._recorders)
        with dmux:
            yield dmux

    def close(self):
        for recorder in self._recorders:
            recorder.close()


class DemuxRecorderSession(BaseRecorderSession):
    '''Demux recorder session.'''
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders
        self._sessions = None
        self._contexts = None

    def __enter__(self):
        self._contexts = [recorder.session() for recorder in self._recorders]
        self._sessions = [context.__enter__() for context in self._contexts]

    def pre_request(self, request):
        for session in self._sessions:
            session.pre_request(request)

    def request(self, request):
        for session in self._sessions:
            session.request(request)

    def request_data(self, data):
        for session in self._sessions:
            session.request_data(data)

    def pre_response(self, response):
        for session in self._sessions:
            session.pre_response(response)

    def response(self, response):
        for session in self._sessions:
            session.response(response)

    def response_data(self, data):
        for session in self._sessions:
            session.response_data(data)

    def begin_control(self, request):
        for session in self._sessions:
            session.begin_control(request)

    def end_control(self, response):
        for session in self._sessions:
            session.end_control(response)

    def request_control_data(self, data):
        for session in self._sessions:
            session.request_control_data(data)

    def response_control_data(self, data):
        for session in self._sessions:
            session.response_control_data(data)

    def __exit__(self, *args):
        for context in self._contexts:
            context.__exit__(*args)
