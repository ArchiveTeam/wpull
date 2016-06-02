import asyncio

from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
from wpull.pipeline.session import ItemSession


class LinkConversionSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_document_converter(session)

    @classmethod
    def _build_document_converter(cls, session: AppSession):
        '''Build the Document Converter.'''

        if not session.args.convert_links:
            return

        converter = session.factory.new(
            'BatchDocumentConverter',
            session.factory['HTMLParser'],
            session.factory['ElementWalker'],
            session.factory['URLTable'],
            backup=session.args.backup_converted
        )

        return converter


class LinkConversionTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        converter = session.factory.instance_map.get(
            'BatchDocumentConverter')

        if converter:
            converter.convert_all()
