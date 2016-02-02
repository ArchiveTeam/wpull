# encoding=utf-8
import random

import asyncio

from wpull.database.sqltable import SQLiteURLTable
from wpull.engine import BaseEngine, Engine
from wpull.stats import Statistics
from wpull.testing.async import AsyncTestCase
import wpull.testing.async


DEFAULT_TIMEOUT = 10


class MockEngineError(Exception):
    pass


class MockEngine(BaseEngine):
    def __init__(self, test_stop=False, test_exception=False):
        super().__init__()
        self.items = [1, 2, 3, 4]
        self.processed_items = []
        self._test_stop = test_stop
        self._test_exception = test_exception

    @asyncio.coroutine
    def _get_item(self):
        if self.items:
            return self.items.pop(0)

    @asyncio.coroutine
    def _process_item(self, item):
        if self._test_stop:
            self._stop()

        self.processed_items.append(item)

        if item == 4:
            self.items.append(5)

            if self._test_exception:
                raise MockEngineError()

        yield from asyncio.sleep(random.uniform(0.01, 0.5))

    @asyncio.coroutine
    def run(self):
        yield from self._run_workers()

    @property
    def concurrent(self):
        return self._concurrent

    @concurrent.setter
    def concurrent(self, num):
        self._set_concurrent(num)


class MockProcessor(object):
    @asyncio.coroutine
    def process(self, url_item):
        url_item.skip()

    def close(self):
        pass


class TestEngine(AsyncTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine(self):
        engine = MockEngine()
        yield from engine.run()

        self.assertFalse(engine.items)
        self.assertEqual([1, 2, 3, 4, 5], engine.processed_items)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine_concurrency_under(self):
        engine = MockEngine()
        engine.concurrent = 2
        yield from engine.run()

        self.assertFalse(engine.items)
        self.assertEqual([1, 2, 3, 4, 5], engine.processed_items)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine_concurrency_equal(self):
        engine = MockEngine()
        engine.concurrent = 4
        yield from engine.run()

        self.assertFalse(engine.items)
        self.assertEqual([1, 2, 3, 4, 5], engine.processed_items)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine_concurrency_over(self):
        engine = MockEngine()
        engine.concurrent = 10
        yield from engine.run()

        self.assertFalse(engine.items)
        self.assertEqual([1, 2, 3, 4, 5], engine.processed_items)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine_stop(self):
        engine = MockEngine(test_stop=True)
        yield from engine.run()
        self.assertEqual([3, 4], engine.items)
        self.assertEqual([1], engine.processed_items)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_base_engine_exception(self):
        engine = MockEngine(test_exception=True)
        try:
            yield from engine.run()
        except MockEngineError:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_engine_bad_url_record(self):
        url_table = SQLiteURLTable(':memory:')
        processor = MockProcessor()
        statistics = Statistics()

        url_table.add_many([
            {'url': 'http://example.........com/invalidurl'},
            {'url': 'http://www.example.comáb©：ðéf'},
            {'url': 'correct horse battery staple'},
        ])

        engine = Engine(url_table, processor, statistics)

        # It shouldn't crash with ValueError during URL parse
        yield from engine()
