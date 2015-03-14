import contextlib
import os

from trollius.coroutines import From, Return

from wpull.driver.phantomjs import PhantomJSDriver, PhantomJSDriverParams
from wpull.testing.goodapp import GoodAppTestCase
import wpull.testing.async
from wpull.testing.util import TempDirMixin


DEFAULT_TIMEOUT = 30


class TestPhantomJS(GoodAppTestCase, TempDirMixin):
    def setUp(self):
        super().setUp()
        self.set_up_temp_dir()

    def tearDown(self):
        super().tearDown()
        self.tear_down_temp_dir()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_driver(self):
        params = PhantomJSDriverParams(
            self.get_url('/static/DEUUEAUGH.html'),
            snapshot_paths=['test.png', 'test.pdf', 'test.html'],
            event_log_filename='event.log',
            action_log_filename='action.log',
            wait_time=0.2,
            custom_headers={
                'X-Doge': 'Wow'
            },
            page_settings={
                'resourceTimeout': 1000
            }
        )

        driver = PhantomJSDriver(params=params)

        yield From(driver.start())
        yield From(driver.process.wait())

        self.assertEqual(0, driver.process.returncode)

        self.assertTrue(os.path.isfile('test.png'))
        self.assertGreater(os.path.getsize('test.png'), 100)
        self.assertTrue(os.path.isfile('test.pdf'))
        self.assertGreater(os.path.getsize('test.pdf'), 100)
        self.assertTrue(os.path.isfile('test.html'))
        self.assertGreater(os.path.getsize('test.html'), 100)

        self.assertTrue(os.path.isfile('action.log'))
        self.assertGreater(os.path.getsize('action.log'), 100)
        self.assertTrue(os.path.isfile('event.log'))
        self.assertGreater(os.path.getsize('event.log'), 100)
