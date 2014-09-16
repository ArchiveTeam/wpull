'''XML document.'''
from wpull.document.base import BaseDocumentDetector
import wpull.string
import wpull.util


class XMLDetector(BaseDocumentDetector):
    @classmethod
    def is_file(cls, file):
        peeked_data = wpull.string.printable_bytes(
            wpull.util.peek_file(file)).lower()

        if b'<?xml' in peeked_data:
            return True

    @classmethod
    def is_request(cls, request):
        return cls.is_url(request.url_info)

    @classmethod
    def is_response(cls, response):
        if 'xml' in response.fields.get('content-type', '').lower():
            return True

        if response.body:
            if cls.is_file(response.body):
                return True

    @classmethod
    def is_url(cls, url_info):
        path = url_info.path.lower()
        if path.endswith('.xml'):
            return True
