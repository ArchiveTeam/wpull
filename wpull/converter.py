# encoding=utf-8
import abc


class BaseDocumentConverter(object, metaclass=abc.ABCMeta):
    pass


class LocalHTMLConverter(BaseDocumentConverter):
    # TODO: convert links to local
    pass
