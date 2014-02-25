# encoding=utf-8
import tornado.testing

from wpull.phantomjs import PhantomJSRemote


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
        remote = PhantomJSRemote()

        yield remote.call('page.open', 'http://example.invalid')

        rpc_info = yield remote.wait_page_event('load_finished')

        self.assertEqual('fail', rpc_info['status'])

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_page_reset(self):
        remote = PhantomJSRemote()

        yield remote.call('reset_page')
