import abc
import contextlib


class BaseRecorder(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    @contextlib.contextmanager
    def session(self):
        pass


class BaseRecorderSession(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def request(self, request):
        pass

    @abc.abstractmethod
    def request_data(self, data):
        pass

    @abc.abstractmethod
    def response(self, response):
        pass

    @abc.abstractmethod
    def response_data(self, data):
        pass


class DemuxRecorder(BaseRecorder):
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders

    @contextlib.contextmanager
    def session(self):
        dmux = DemuxRecorderSession(self._recorders)
        with dmux:
            yield dmux


class DemuxRecorderSession(BaseRecorderSession):
    def __init__(self, recorders):
        super().__init__()
        self._recorders = recorders
        self._sessions = None
        self._contexts = None

    def __enter__(self):
        self._contexts = [recorder.session() for recorder in self._recorders]
        self._sessions = [context.__enter__() for context in self._contexts]

    def request(self, request):
        for session in self._sessions:
            session.request(request)

    def request_data(self, data):
        for session in self._sessions:
            session.request_data(data)

    def response(self, response):
        for session in self._sessions:
            session.response(response)

    def response_data(self, data):
        for session in self._sessions:
            session.response_data(data)

    def __exit__(self, *args):
        for context in self._contexts:
            context.__exit__(*args)


class WARCRecorder(BaseRecorder):
    pass


class DebugPrintRecorder(BaseRecorder):
    @contextlib.contextmanager
    def session(self):
        print('Session started')
        try:
            yield DebugPrintRecorderSession()
        finally:
            print('Session ended')


class DebugPrintRecorderSession(BaseRecorderSession):
    def request(self, request):
        print(request)

    def request_data(self, data):
        print(data)

    def response(self, response):
        print(response)

    def response_data(self, data):
        print(data)


class PrintServerResponseRecorder(BaseRecorder):
    @contextlib.contextmanager
    def session(self):
        yield PrintServerResponseRecorderSession()


class PrintServerResponseRecorderSession(BaseRecorderSession):
    def request(self, request):
        pass

    def request_data(self, data):
        pass

    def response(self, response):
        print(''.join(data.decode() for data in response.iter_header()))

    def response_data(self, data):
        pass
