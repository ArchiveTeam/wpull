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
            yield From(driver.snapshot('asdf.png'))
            yield From(driver.snapshot('asdf.pdf'))
            yield From(driver.snapshot('asdf.html'))
            yield From(driver.close_page())
            driver.close()

            self.assertTrue(os.path.isfile('asdf.png'))
            self.assertGreater(os.path.getsize('asdf.png'), 100)
            self.assertTrue(os.path.isfile('asdf.pdf'))
            self.assertGreater(os.path.getsize('asdf.pdf'), 100)
            self.assertTrue(os.path.isfile('asdf.html'))
            self.assertGreater(os.path.getsize('asdf.html'), 100)

            self.assertTrue(load_finished)

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

    # @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    # def test_client_with_remote_crash(self):
    #     http_client = Client()
    #     proxy_server = HTTPProxyServer(http_client)
    #     proxy_socket, proxy_host = tornado.testing.bind_unused_port()
    #
    #     yield From(trollius.start_server(proxy_server, sock=proxy_socket))
    #
    #     remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))
    #
    #     with remote_client.remote() as remote:
    #         self.assertIn(remote, remote_client.remotes_busy)
    #
    #         try:
    #             yield From(remote.eval('phantom.exit(1)'))
    #         except PhantomJSRPCTimedOut:
    #             # It probably quit before it could reply
    #             pass
    #         except PhantomJSRPCError:
    #             # PhantomJS 1.9.8+: Ignore 'undefined' error.
    #             pass
    #
    #         yield From(trollius.sleep(0.1))
    #
    #         test_remote = remote
    #
    #     self.assertNotIn(test_remote, remote_client.remotes_ready)
    #     self.assertNotIn(test_remote, remote_client.remotes_busy)
    #
    #     remote_client.close()
    #
    # @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    # def test_client_with_remote_crash_later(self):
    #     http_client = Client()
    #     proxy_server = HTTPProxyServer(http_client)
    #     proxy_socket, proxy_host = tornado.testing.bind_unused_port()
    #
    #     yield From(trollius.start_server(proxy_server, sock=proxy_socket))
    #
    #     remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))
    #
    #     with remote_client.remote() as remote:
    #         self.assertIn(remote, remote_client.remotes_busy)
    #
    #         test_remote = remote
    #
    #     yield From(trollius.sleep(0.1))
    #
    #     try:
    #         yield From(test_remote.eval('phantom.exit(1)'))
    #     except PhantomJSRPCTimedOut:
    #         # It probably quit before it could reply
    #         pass
    #     except PhantomJSRPCError:
    #         # PhantomJS 1.9.8+: Ignore 'undefined' error.
    #         pass
    #
    #     with remote_client.remote() as remote:
    #         self.assertIn(remote, remote_client.remotes_busy)
    #
    #     self.assertNotIn(test_remote, remote_client.remotes_ready)
    #     self.assertNotIn(test_remote, remote_client.remotes_busy)
    #
    #     remote_client.close()
    #
    # @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    # def test_timeouts(self):
    #     remote = PhantomJSRemote()
    #
    #     try:
    #         yield From(remote.wait_page_event('invalid_event', timeout=0.1))
    #     except PhantomJSRPCTimedOut:
    #         pass
    #     else:
    #         self.fail()  # pragma: no cover
    #
    #     @trollius.coroutine
    #     def mock_put_rpc_info(rpc_info):
    #         '''Discard any RPC to be sent to the subprocesss.'''
    #         return trollius.Event()
    #
    #     remote._put_rpc_info = mock_put_rpc_info
    #
    #     try:
    #         yield From(trollius.async(remote.eval('blah', timeout=0.1)))
    #     except PhantomJSRPCTimedOut:
    #         pass
    #     else:
    #         self.fail()  # pragma: no cover
    #
    #     try:
    #         yield From(remote.set('blah', 123, timeout=0.1))
    #     except PhantomJSRPCTimedOut:
    #         pass
    #     else:
    #         self.fail()  # pragma: no cover
    #
    #     try:
    #         yield From(remote.call('blah', timeout=0.1))
    #     except PhantomJSRPCTimedOut:
    #         pass
    #     else:
    #         self.fail()  # pragma: no cover
    #
    # @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    # def test_multiline(self):
    #     remote = PhantomJSRemote()
    #
    #     code = "new Array(9001).join('a');"
    #     result = yield From(trollius.async(remote.eval(code)))
    #
    #     self.assertEqual('a' * 9000, result)
