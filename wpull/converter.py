# encoding=utf-8
'''Document content post-processing.'''
import abc


class BaseDocumentConverter(object, metaclass=abc.ABCMeta):
    '''Base class for classes that convert a document format.'''
    @abc.abstractmethod
    def convert(self, input_file, output_file):
        pass


class LocalHTMLConverter(BaseDocumentConverter):
    # TODO: convert links to local
    def convert(self, input_file, output_file):
        raise NotImplementedError()
