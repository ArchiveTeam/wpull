'''Request object abstractions'''
import abc


class CommonMixin(object):
    @abc.abstractmethod
    def to_dict(self):
        '''Convert to a dict suitable for JSON.'''

    @abc.abstractmethod
    def to_bytes(self):
        '''Serialize to HTTP bytes.'''

    @abc.abstractmethod
    def parse(self, data):
        '''Parse from HTTP bytes.'''
