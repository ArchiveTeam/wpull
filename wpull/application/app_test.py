import asyncio

from typing import Optional

import wpull.testing.async
from wpull.application.app import Application
from wpull.pipeline.pipeline import Pipeline, ItemSource, ItemTask, \
    PipelineSeries


class MyItemTask(ItemTask[int]):
    def __init__(self, callback=None):
        self.callback = callback

    @asyncio.coroutine
    def process(self, work_item: int):
        if self.callback:
            self.callback(work_item)


class MyItemSource(ItemSource[int]):
    def __init__(self, values):
        self.values = list(values)

    @asyncio.coroutine
    def get_item(self) -> Optional[int]:
        if self.values:
            return self.values.pop(0)


class TestAppliation(wpull.testing.async.AsyncTestCase):
    @wpull.testing.async.async_test()
    def test_simple(self):
        source1 = MyItemSource([1, 2, 3])
        source2 = MyItemSource([4, 5, 6])

        pipeline1 = Pipeline(source1, [MyItemTask()])
        pipeline2 = Pipeline(source2, [MyItemTask()])

        app = Application(PipelineSeries([pipeline1, pipeline2]))

        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test()
    def test_exit_codes(self):
        for error_class, expected_exit_code in Application.ERROR_CODE_MAP.items():
            with self.subTest(error_class):
                source = MyItemSource([1, 2, 3])

                def callback(work_item):
                    raise error_class(work_item)

                task = MyItemTask(callback=callback)
                pipeline = Pipeline(source, [task])
                app = Application(PipelineSeries([pipeline]))

                exit_code = yield from app.run()

                self.assertEqual(expected_exit_code, exit_code)

    @wpull.testing.async.async_test()
    def test_pipeline_skipping(self):
        source1 = MyItemSource([1, 2, 3])
        source2 = MyItemSource([4, 5, 6])
        source3 = MyItemSource([7, 8, 9])

        task1 = MyItemTask()

        pipeline1 = Pipeline(source1, [task1])
        pipeline2 = Pipeline(source2, [MyItemTask()])
        pipeline3 = Pipeline(source3, [MyItemTask()])

        pipeline2.skippable = True

        app = Application(PipelineSeries([pipeline1, pipeline2, pipeline3]))

        def callback(work_item):
            app.stop()

        task1.callback = callback

        yield from app.run()

        self.assertTrue(source1.values, 'unprocessed')
        self.assertTrue(source2.values, 'skipped')
        self.assertFalse(source3.values, 'processed',)
