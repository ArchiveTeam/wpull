# encoding=utf-8
import tornado.testing
from trollius import From
import trollius

from wpull.http.client import Client
from wpull.driver.phantomjs import (PhantomJSRemote, PhantomJSClient,
                             PhantomJSRPCTimedOut, PhantomJSRPCError)
from wpull.proxy import HTTPProxyServer
import wpull.testing.async


DEFAULT_TIMEOUT = 30


class TestPhantomJS(wpull.testing.async.AsyncTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_rpc(self):
        remote = PhantomJSRemote()

        result = yield From(remote.call('debugEcho', 'hello!'))

        self.assertEqual('hello!', result)

        yield From(remote.eval('var myvalue;'))
        yield From(remote.set('myvalue', 123))

        result = yield From(remote.eval('myvalue'))

        self.assertEqual(123, result)

        yield From(remote.set('myvalue', 'abc'))

        result = yield From(remote.eval('myvalue'))

        self.assertEqual('abc', result)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_events(self):
        remote = PhantomJSRemote(
            page_settings={'userAgent': 'Blah'},
            default_headers={'Accept-Encoding': 'identity'},
        )

        yield From(remote.call('page.open', 'http://example.invalid'))

        rpc_info = yield From(remote.wait_page_event('load_finished'))

        self.assertEqual('fail', rpc_info['status'])

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_page_reset(self):
        remote = PhantomJSRemote()

        yield From(remote.call('resetPage'))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client(self):
        http_client = Client()
        proxy_server = HTTPProxyServer(http_client)
        proxy_socket, proxy_host = tornado.testing.bind_unused_port()

        yield From(trollius.start_server(proxy_server, sock=proxy_socket))

        remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))

        with remote_client.remote() as remote:
            self.assertIn(remote, remote_client.remotes_busy)

            test_remote = remote

        for dummy in range(100):
            if test_remote in remote_client.remotes_ready:
                break

            yield From(trollius.sleep(0.1))

        self.assertIn(test_remote, remote_client.remotes_ready)
        self.assertNotIn(test_remote, remote_client.remotes_busy)

        remote_client.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client_with_remote_crash(self):
        http_client = Client()
        proxy_server = HTTPProxyServer(http_client)
        proxy_socket, proxy_host = tornado.testing.bind_unused_port()

        yield From(trollius.start_server(proxy_server, sock=proxy_socket))

        remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))

        with remote_client.remote() as remote:
            self.assertIn(remote, remote_client.remotes_busy)

            try:
                yield From(remote.eval('phantom.exit(1)'))
            except PhantomJSRPCTimedOut:
                # It probably quit before it could reply
                pass
            except PhantomJSRPCError:
                # PhantomJS 1.9.8+: Ignore 'undefined' error.
                pass

            yield From(trollius.sleep(0.1))

            test_remote = remote

        self.assertNotIn(test_remote, remote_client.remotes_ready)
        self.assertNotIn(test_remote, remote_client.remotes_busy)

        remote_client.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_client_with_remote_crash_later(self):
        http_client = Client()
        proxy_server = HTTPProxyServer(http_client)
        proxy_socket, proxy_host = tornado.testing.bind_unused_port()

        yield From(trollius.start_server(proxy_server, sock=proxy_socket))

        remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))

        with remote_client.remote() as remote:
            self.assertIn(remote, remote_client.remotes_busy)

            test_remote = remote

        yield From(trollius.sleep(0.1))

        try:
            yield From(test_remote.eval('phantom.exit(1)'))
        except PhantomJSRPCTimedOut:
            # It probably quit before it could reply
            pass
        except PhantomJSRPCError:
            # PhantomJS 1.9.8+: Ignore 'undefined' error.
            pass

        with remote_client.remote() as remote:
            self.assertIn(remote, remote_client.remotes_busy)

        self.assertNotIn(test_remote, remote_client.remotes_ready)
        self.assertNotIn(test_remote, remote_client.remotes_busy)

        remote_client.close()

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_timeouts(self):
        remote = PhantomJSRemote()

        try:
            yield From(remote.wait_page_event('invalid_event', timeout=0.1))
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

        @trollius.coroutine
        def mock_put_rpc_info(rpc_info):
            '''Discard any RPC to be sent to the subprocesss.'''
            return trollius.Event()

        remote._put_rpc_info = mock_put_rpc_info

        try:
            yield From(trollius.async(remote.eval('blah', timeout=0.1)))
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

        try:
            yield From(remote.set('blah', 123, timeout=0.1))
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

        try:
            yield From(remote.call('blah', timeout=0.1))
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()  # pragma: no cover

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_multiline(self):
        remote = PhantomJSRemote()

        code = "new Array(9001).join('a');"
        result = yield From(trollius.async(remote.eval(code)))

        self.assertEqual('a' * 9000, result)
