'''Resource tracking.'''
import abc
import time


class ResourceState(object):
    '''Resource states'''
    pending = 'pending'
    '''Resource is being fetched.'''
    loaded = 'loaded'
    '''Resource has been fetched.'''
    error = 'error'
    '''An error occured fetching the resource.'''


class Resource(object):
    '''Represents a WebKit resource.

    Attributes:
        id: Unique identifier for the resource request.
        url (str): URL of the request.
        status_code (int): HTTP status code.
        status_reason (str): HTTP status reason line.
        body_size (int): Size of content.
        touch_timestamp (int): Timestamp of last request activity.
        state (ResourceState): State of the resource request.
    '''

    def __init__(self, resource_id, url):
        self.id = resource_id
        self.url = url
        self.status_code = None
        self.status_reason = None
        self.body_size = 0
        self.touch_timestamp = time.time()
        self.state = ResourceState.pending

    def start(self):
        '''Set resource request as pending.'''
        self.touch_timestamp = time.time()
        self.state = ResourceState.pending

    def touch(self):
        '''Update the timestamp.'''
        self.touch_timestamp = time.time()

    def end(self):
        '''Set resource request as loaded.'''
        self.touch_timestamp = time.time()
        self.state = ResourceState.loaded

    def error(self):
        '''Set resource request as error.'''
        self.touch_timestamp = time.time()
        self.state = ResourceState.error


class ResourceTracker(object, metaclass=abc.ABCMeta):
    '''WebKit resource tracker.

    Attributes:
        resources (dict): Mapping from ID to Resource.
        pending (set): Set of pending Resources.
        error (set): Set of errored Resources.
        loaded (set): Set of loaded Resources.
    '''

    def __init__(self):
        self._resources = {}
        self._pending = set()
        self._error = set()
        self._loaded = set()

    @property
    def resources(self):
        return self._resources

    @property
    def pending(self):
        return self._pending

    @property
    def error(self):
        return self._error

    @property
    def loaded(self):
        return self._loaded

    def reset(self):
        '''Reset tracker to 0 values.'''
        self._resources.clear()
        self._pending.clear()
        self._error.clear()
        self._loaded.clear()

    @abc.abstractmethod
    def process_request(self, request):
        '''Process resource request.'''

    @abc.abstractmethod
    def process_response(self, response):
        '''Process resource response.'''

    @abc.abstractmethod
    def process_error(self, resource_error):
        '''Process resource error.'''


class PhantomJSResourceTracker(ResourceTracker):
    '''PhantomJS resource tracker.'''
    def process_request(self, request):
        resource = Resource(request['id'], request['url'])
        self._resources[resource.id] = resource
        self._pending.add(resource)
        resource.start()

    def process_response(self, response):
        resource = self._resources[response['id']]

        if response['stage'] == 'end':
            resource.end()
            self._pending.remove(resource)
            self._loaded.add(resource)
        else:
            resource.touch()

    def process_error(self, resource_error):
        resource = self._resources[resource_error['id']]

        resource.error()
        self._pending.remove(resource)
        self._error.add(resource)


class PySideResourceTracker(ResourceTracker):
    pass
