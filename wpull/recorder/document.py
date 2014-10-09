'''Documents as a stream.'''


import contextlib

from wpull.recorder.base import BaseRecorder, BaseRecorderSession
import wpull.util


class OutputDocumentRecorder(BaseRecorder):
    '''Output documents as a stream.'''
    def __init__(self, file, with_headers=False):
        self._file = file
        self._with_headers = with_headers

    @contextlib.contextmanager
    def session(self):
        yield OutputDocumentRecorderSession(self._file, self._with_headers)

    def close(self):
        self._file.close()


class OutputDocumentRecorderSession(BaseRecorderSession):
    '''Output document recorder session.'''
    def __init__(self, file, with_headers=False):
        self._file = file
        self._with_headers = with_headers
        self._response = None

    def pre_response(self, response):
        self._response = response

    def response_data(self, data):
        if self._with_headers and not self._response:
            self._file.write(data)

        if self._response:
            with wpull.util.reset_file_offset(self._response.body):
                self._file.write(self._response.body.read(len(data)))
