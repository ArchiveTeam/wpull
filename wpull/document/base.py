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


class BaseDocumentReader(BaseDocumentDetector):
    '''Base class for classes that read documents.'''

    @abc.abstractmethod
    def read_links(self, file, encoding=None):
        '''Return an iterator of links found in the document.

        Args:
            file: A file object containing the document.
            encoding (str): The encoding of the document.

        The items returned will depend on the implementation.
        '''
        pass
