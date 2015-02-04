'''Request object abstractions'''
import abc

from wpull.url import URLInfo


class DictableMixin(object):
    @abc.abstractmethod
    def to_dict(self):
        '''Convert to a dict suitable for JSON.'''

    @classmethod
    def call_to_dict_or_none(cls, instance):
        '''Call ``to_dict`` or return ``None``.'''
        if hasattr(instance, 'to_dict'):
            return instance.to_dict()


class SerializableMixin(object):
    '''Serialize and unserialize methods.'''
    @abc.abstractmethod
    def to_bytes(self):
        '''Serialize to HTTP bytes.'''

    @abc.abstractmethod
    def parse(self, data):
        '''Parse from HTTP bytes.'''


class URLPropertyMixin(object):
    '''Provide URL as a property.

    Attributes:
        url (str): The complete URL string.
        url_info (:class:`.url.URLInfo`): The URLInfo of the `url` attribute.

    Setting :attr:`url` or :attr:`url_info` will update the other
        respectively.
    '''
    def __init__(self):
        self._url = None
        self._url_info = None

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, url_str):
        self._url = url_str
        self._url_info = URLInfo.parse(url_str)

    @property
    def url_info(self):
        return self._url_info

    @url_info.setter
    def url_info(self, url_info):
        self._url_info = url_info
        self._url = url_info.url


class ProtocolResponseMixin(object):
    '''Protocol abstraction for response objects.'''
    @abc.abstractproperty
    def protocol(self):
        '''Return the name of the protocol.'''

    @abc.abstractmethod
    def response_code(self):
        '''Return the response code representative for the protocol.'''

    @abc.abstractmethod
    def response_message(self):
        '''Return the response message representative for the protocol.'''
