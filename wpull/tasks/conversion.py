import asyncio

from wpull.pipeline.pipeline import ItemTask


class LinkConversionTask(ItemTask):
    def __init__(self, converter):
        self._converter = converter

    @asyncio.coroutine
    def process(self, work_item: WorkItemT):
        # TODO:
        pass

    def _convert_documents(self):
        converter = self._builder.factory.instance_map.get(
            'BatchDocumentConverter')

        if converter:
            converter.convert_all()
