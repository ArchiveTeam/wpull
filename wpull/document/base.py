'''Document bases.'''
import abc


class BaseDocumentDetector(object, metaclass=abc.ABCMeta):
    '''Base class for classes that detect document types.'''

    @classmethod
    def is_supported(cls, file=None, request=None, response=None,
                     url_info=None):
        '''Given the hints, return whether the document is supported.

        Args:
            file: A file object containing the document.
            request (:class:`.http.request.Request`): An HTTP request.
            response (:class:`.http.request.Response`): An HTTP response.
            url_info (:class:`.url.URLInfo`): A URLInfo.

        Returns:
            bool: If True, the reader should be able to read it.
        '''
        if response:
            try:
                if cls.is_response(response):
                    return True
            except NotImplementedError:
                pass

        if file:
            try:
                if cls.is_file(file):
                    return True
            except NotImplementedError:
                pass

        if request:
            try:
                if cls.is_request(request):
                    return True
            except NotImplementedError:
                pass

        if url_info:
            try:
                if cls.is_url(url_info):
                    return True
            except NotImplementedError:
                pass

    @classmethod
    def is_file(cls, file):
        '''Return whether the reader is likely able to read the file.

        Args:
            file: A file object containing the document.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_request(cls, request):
        '''Return whether the request is likely supported.

        Args:
            request (:class:`.http.request.Request`): An HTTP request.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_response(cls, response):
        '''Return whether the response is likely able to be read.

        Args:
            response (:class:`.http.request.Response`): An HTTP response.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override

    @classmethod
    def is_url(cls, url_info):
        '''Return whether the URL is likely to be supported.

        Args:
            url_info (:class:`.url.URLInfo`): A URLInfo.

        Returns:
            bool
        '''
        raise NotImplementedError()  # optional override


class BaseTextStreamReader(object, metaclass=abc.ABCMeta):
    '''Base class for document readers that filters link and non-link text.'''
    @abc.abstractmethod
    def iter_text(self, file, encoding=None):
        '''Return the file text and links.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterator: Each item is a tuple:

            1. str: The text
            2. bool (or truthy value): Whether the text is a likely a link.
               If truthy value may be provided containing additional context
               of the link.

        The links returned are raw text and will require further processing.
        '''

    def iter_links(self, file, encoding=None, context=False):
        '''Return the links.

        This function is a convenience function for calling :meth:`iter_text`
        and returning only the links.
        '''
        if context:
            return [item for item in self.iter_text(file, encoding) if item[1]]
        else:
            return [item[0] for item in self.iter_text(file, encoding) if item[1]]


class BaseExtractiveReader(object, metaclass=abc.ABCMeta):
    '''Base class for document readers that can only extract links.'''
    def iter_links(self, file, encoding=None):
        '''Return links from file.

        Returns:
            iterator: Each item is a str which represents a link.
        '''


class BaseHTMLReader(object, metaclass=abc.ABCMeta):
    '''Base class for document readers for handling SGML-like documents.'''

    @abc.abstractmethod
    def iter_elements(self, file, encoding=None):
        '''Return an iterator of elements found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        Returns:
            iterator: Each item is an element from
            :mod:`.document.htmlparse.element`
        '''
        pass
