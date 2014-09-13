import abc


class BaseParser(object, metaclass=abc.ABCMeta):
    def parse(self, file, encoding=None):
        '''Parse the document for elements.

        Returns:
            iterator: Each item is from
            :module:`.document.htmlparse.element`
        '''

    @abc.abstractproperty
    def parser_error(self):
        '''Return the Exception class for parsing errors.'''
