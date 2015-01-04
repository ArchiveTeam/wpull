# encoding=utf-8
import contextlib
import os
from tempfile import TemporaryDirectory
import tornado.testing
from trollius import From
import trollius

from wpull.http.client import Client
from wpull.driver.phantomjs import (PhantomJSDriver,
                             PhantomJSRPCTimedOut, PhantomJSRPCError,
                             PhantomJSPool)
from wpull.proxy import HTTPProxyServer
import wpull.testing.async
from wpull.testing.goodapp import GoodAppTestCase


DEFAULT_TIMEOUT = 30

@contextlib.contextmanager
def cd_tempdir():
    original_dir = os.getcwd()
    with TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(original_dir)


class TestPhantomJS(GoodAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_rpc(self):
        driver = PhantomJSDriver(
            page_settings={'userAgent': 'Blah'},
            default_headers={'Accept-Encoding': 'identity'},
        )
        load_finished = False

        def load_finished_callback(message):
            nonlocal load_finished
            load_finished = True

        driver.page_event_handlers['load_finished'] = load_finished_callback

        with cd_tempdir():
            yield From(driver.start())
            yield From(driver.open_page(self.get_url('/')))
            yield From(driver.scroll_to(0, 100))

            for dummy in range(50):
                if not load_finished:
                    yield From(trollius.sleep(0.1))
                else:
                    break
            else:
                print('Load did not finish!')

            yield From(driver.snapshot('asdf.png'))
            yield From(driver.snapshot('asdf.pdf'))
            yield From(driver.snapshot('asdf.html'))
            page_url = yield From(driver.get_page_url())

            yield From(driver.close_page())
            driver.close()

            self.assertTrue(os.path.isfile('asdf.png'))
            self.assertGreater(os.path.getsize('asdf.png'), 100)
            self.assertTrue(os.path.isfile('asdf.pdf'))
            self.assertGreater(os.path.getsize('asdf.pdf'), 100)
            self.assertTrue(os.path.isfile('asdf.html'))
            self.assertGreater(os.path.getsize('asdf.html'), 100)

            self.assertTrue(load_finished)

            self.assertEqual(self.get_url('/'), page_url)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_process_reuse(self):
        driver = PhantomJSDriver()

        with cd_tempdir():
            yield From(driver.start())
            yield From(driver.open_page(self.get_url('/')))
            yield From(driver.start())
            yield From(driver.open_page(self.get_url('/')))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_pool(self):
        pool = PhantomJSPool()

        with pool.session() as driver:
            self.assertIn(driver, pool.drivers_busy)
            self.assertNotIn(driver, pool.drivers_ready)

            test_driver = driver

        self.assertIn(test_driver, pool.drivers_ready)
        self.assertNotIn(test_driver, pool.drivers_busy)

        pool.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_pool_exception(self):
        pool = PhantomJSPool()

        try:
            with pool.session() as driver:
                self.assertIn(driver, pool.drivers_busy)
                self.assertNotIn(driver, pool.drivers_ready)

                test_driver = driver

                raise ValueError('much crash')
        except ValueError:
            pass

        self.assertIn(test_driver, pool.drivers_ready)
        self.assertNotIn(test_driver, pool.drivers_busy)

        pool.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_pool_with_driver_crash(self):
        pool = PhantomJSPool()

        with pool.session() as driver:
            self.assertIn(driver, pool.drivers_busy)
            self.assertNotIn(driver, pool.drivers_ready)

            yield From(driver.start())

            # Simulate crash
            driver.close()

            for dummy in range(50):
                if driver.return_code is not None:
                    break
                else:
                    yield From(trollius.sleep(0.1))
            else:
                print('Did not close!')

            test_driver = driver

        self.assertNotIn(test_driver, pool.drivers_busy)
        self.assertNotIn(test_driver, pool.drivers_ready)

        pool.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client_with_driver_crash_later(self):
        pool = PhantomJSPool()

        with pool.session() as driver:
            self.assertIn(driver, pool.drivers_busy)

            yield From(driver.start())

            test_driver = driver

        yield From(trollius.sleep(0.1))

        # Simulate crash
        test_driver.close()

        for dummy in range(50):
            if test_driver.return_code is not None:
                break
            else:
                yield From(trollius.sleep(0.1))
        else:
            print('Did not close!')

        with pool.session() as driver:
            self.assertNotEqual(test_driver, driver)
            self.assertIn(driver, pool.drivers_busy)

        self.assertNotIn(test_driver, pool.drivers_ready)
        self.assertNotIn(test_driver, pool.drivers_busy)

        pool.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_timeouts(self):
        driver = PhantomJSDriver(rpc_timeout=0)

        with cd_tempdir():
            yield From(driver.start())

            try:
                yield From(driver.open_page(self.get_url('/')))
            except PhantomJSRPCTimedOut:
                pass
            else:
                self.fail()  # pragma: no-cover
