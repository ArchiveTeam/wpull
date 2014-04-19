# encoding=utf-8
import tornado.testing

import wpull.async
from wpull.http.client import Client
from wpull.phantomjs import (PhantomJSRemote, PhantomJSClient,
    PhantomJSRPCTimedOut)
from wpull.proxy import HTTPProxyServer


DEFAULT_TIMEOUT = 30


class TestPhantomJS(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_rpc(self):
        remote = PhantomJSRemote()

        result = yield remote.call('debugEcho', 'hello!')

        self.assertEqual('hello!', result)

        yield remote.eval('var myvalue;')
        yield remote.set('myvalue', 123)

        result = yield remote.eval('myvalue')

        self.assertEqual(123, result)

        yield remote.set('myvalue', 'abc')

        result = yield remote.eval('myvalue')

        self.assertEqual('abc', result)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_events(self):
        remote = PhantomJSRemote(
            page_settings={'userAgent': 'Blah'},
            default_headers={'Accept-Encoding': 'identity'},
        )

        yield remote.call('page.open', 'http://example.invalid')

        rpc_info = yield remote.wait_page_event('load_finished')

        self.assertEqual('fail', rpc_info['status'])

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_page_reset(self):
        remote = PhantomJSRemote()

        yield remote.call('resetPage')

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_client(self):
        http_client = Client()
        proxy_server = HTTPProxyServer(http_client)
        proxy_socket, proxy_host = tornado.testing.bind_unused_port()

        proxy_server.add_socket(proxy_socket)

        remote_client = PhantomJSClient('localhost:{0}'.format(proxy_host))

        with remote_client.remote() as remote:
            self.assertIn(remote, remote_client.remotes_busy)

            test_remote = remote

        for dummy in range(100):
            if test_remote in remote_client.remotes_ready:
                break

            yield wpull.async.sleep(0.1)

        self.assertIn(test_remote, remote_client.remotes_ready)
        self.assertNotIn(test_remote, remote_client.remotes_busy)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_timeouts(self):
        remote = PhantomJSRemote()

        try:
            yield remote.wait_page_event('invalid_event', timeout=0.1)
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()

        try:
            future = remote.eval('blah', timeout=0.1)
            remote._rpc_reply_map.clear()
            yield future
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()

        try:
            future = remote.set('blah', 123, timeout=0.1)
            remote._rpc_reply_map.clear()
            yield future
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()

        try:
            future = remote.call('blah', timeout=0.1)
            remote._rpc_reply_map.clear()
            yield future
        except PhantomJSRPCTimedOut:
            pass
        else:
            self.fail()
