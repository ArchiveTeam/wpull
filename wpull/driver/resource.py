'''Resource tracking.'''
import abc
import time


class ResourceState(object):
    pending = 'pending'
    loaded = 'loaded'
    error = 'error'


class Resource(object):
    '''Represents a WebKit resource.'''

    def __init__(self, resource_id, url):
        self.id = resource_id
        self.url = url
        self.status_code = None
        self.status_reason = None
        self.body_size = 0
        self.touch_timestamp = time.time()
        self.state = ResourceState.pending

    def start(self, status_code, status_reason):
        self.touch_timestamp = time.time()
        self.status_code = status_code
        self.status_reason = status_reason

    def end(self):
        self.touch_timestamp = time.time()
        self.state = ResourceState.loaded

    def error(self):
        self.touch_timestamp = time.time()
        self.state = ResourceState.error


class ResourceTracker(object, metaclass=abc.ABCMeta):
    '''WebKit resource tracker.'''

    def __init__(self):
        self._resources = {}
        self._pending = set()
        self._error = set()
        self._loaded = set()

    @property
    def resources(self):
        return self._resources

    def pending(self):
        return self._pending

    def error(self):
        return self._error

    def loaded(self):
        return self._loaded

    @abc.abstractmethod
    def process_request(self, request):
        pass

    @abc.abstractmethod
    def process_reply(self, reply):
        pass


class PhantomJSResourceTracker(ResourceTracker):
    pass


class PySideResourceTracker(ResourceTracker)
    pass
