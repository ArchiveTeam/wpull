# encoding=utf-8
'''Protocol interaction session elements.'''
import abc


class BaseRequest(object, metaclass=abc.ABCMeta):
    '''Base class for Requests.

    This class has no purpose yet.
    '''
    pass


class BaseResponse(object, metaclass=abc.ABCMeta):
    '''Base class for Response.

    This class has no purpose yet.
    '''
    pass


class BaseClient(object, metaclass=abc.ABCMeta):
    '''Base class for clients.

    This class has no purpose yet.
    '''
    pass
