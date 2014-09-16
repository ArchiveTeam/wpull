import contextlib

from wpull.recorder.base import BaseRecorder, BaseRecorderSession
from wpull.recorder.base_test import BaseRecorderTest
from wpull.recorder.demux import DemuxRecorder


class MockRecorderError(Exception):
    pass


class MockRecorder(BaseRecorder):
    def __init__(self, broken=False):
        self.broken = broken
        self.session_obj = None

    @contextlib.contextmanager
    def session(self):
        if self.broken:
            self.session_obj = MockBrokenRecorderSession()
        else:
            self.session_obj = MockRecorderSession()
        try:
            yield self.session_obj
        finally:
            self.session_obj.close()


class MockBrokenRecorderSession(BaseRecorderSession):
    def __init__(self):
        self.closed = False

    def pre_request(self, request):
        raise MockRecorderError()

    def close(self):
        self.closed = True


class MockRecorderSession(BaseRecorderSession):
    def __init__(self):
        self.ok = False
        self.closed = False

    def pre_request(self, request):
        self.ok = True

    def close(self):
        self.closed = True


class TestDemux(BaseRecorderTest):
    def test_demux_recorder(self):
        broken_recorder = MockRecorder(broken=True)
        good_recorder = MockRecorder(broken=False)
        demux_recorder = DemuxRecorder([broken_recorder, good_recorder])

        try:
            with demux_recorder.session() as session:
                session.pre_request(None)
        except MockRecorderError:
            pass

        self.assertTrue(broken_recorder.session_obj.closed)
        self.assertTrue(good_recorder.session_obj.closed)
        self.assertFalse(good_recorder.session_obj.ok)
