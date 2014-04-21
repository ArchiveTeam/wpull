# encoding=utf-8
import datetime
import time

import tornado.testing
import toro

from wpull.async import sleep, wait_future, TimedOut, AdjustableSemaphore


DEFAULT_TIMEOUT = 30


class TestUtilAsync(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test
    def test_sleep(self):
        start_time = time.time()
        yield sleep(1.0)
        end_time = time.time()

        self.assertAlmostEqual(1.0, end_time - start_time, delta=0.5)

    @tornado.testing.gen_test
    def test_wait_future(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)

        yield wait_future(test_func(), 2)

    @tornado.testing.gen_test
    def test_wait_future_none(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)

        yield wait_future(test_func(), None)

    @tornado.testing.gen_test
    def test_wait_future_timeout(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(60.0)

        try:
            yield wait_future(test_func(), 0.1)
        except TimedOut:
            pass
        else:
            self.assertTrue(False)

    @tornado.testing.gen_test
    def test_wait_future_error(self):
        @tornado.gen.coroutine
        def test_func():
            yield sleep(0.1)
            raise ValueError('uh-oh')

        try:
            yield wait_future(test_func(), 2.0)
        except ValueError as error:
            self.assertEqual('uh-oh', error.args[0])
        else:
            self.assertTrue(False)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_adjustable_semaphore(self):
        semaphore = AdjustableSemaphore(value=2)

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 1
        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 2

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.set_max(3)
        self.assertEqual(3, semaphore.max)

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))  # value = 3

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.set_max(1)
        self.assertEqual(1, semaphore.max)

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 2

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 1

        try:
            yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))
        except toro.Timeout:
            pass
        else:
            self.fail()

        semaphore.release()  # value = 0

        yield semaphore.acquire(deadline=datetime.timedelta(seconds=0.1))

        semaphore.release()

        self.assertRaises(ValueError, semaphore.release)

        def set_neg_max():
            semaphore.set_max(-1)

        self.assertRaises(ValueError, set_neg_max)
