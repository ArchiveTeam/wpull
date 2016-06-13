import asyncio
from typing import Optional

from wpull.database.base import NotFound
from wpull.pipeline.item import URLRecord
from wpull.pipeline.pipeline import ItemTask, ItemSource
from wpull.pipeline.app import AppSession


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


class QueuedFileSession(object):
    def __init__(self, app_session: AppSession, file_id: int,
                 url_record: URLRecord):
        self.app_session = app_session
        self.file_id = file_id
        self.url_record = url_record


class QueuedFileSource(ItemSource[QueuedFileSession]):
    def __init__(self, app_session: AppSession):
        self._app_session = app_session

    @asyncio.coroutine
    def get_item(self) -> Optional[QueuedFileSession]:
        if not self._app_session.args.convert_links:
            return

        try:
            db_item = self._app_session.factory['URLTable'].convert_check_out()
        except NotFound:
            return

        session = QueuedFileSession(
            self._app_session, db_item[0], db_item[1])
        return session


class LinkConversionTask(ItemTask[QueuedFileSession]):
    @asyncio.coroutine
    def process(self, session: QueuedFileSession):
        converter = session.app_session.factory.instance_map.get(
            'BatchDocumentConverter')

        if not converter:
            return

        converter.convert_by_record(session.url_record)
