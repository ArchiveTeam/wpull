# encoding=utf-8
import tornado.testing

from wpull.phantomjs import PhantomJS


DEFAULT_TIMEOUT = 30


class TestPhantomJS(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_rpc(self):
        phantomjs = PhantomJS()

        result = yield phantomjs.call('debugEcho', 'hello!')

        self.assertEqual('hello!', result)

        yield phantomjs.eval('var myvalue;')
        yield phantomjs.set('myvalue', 123)

        result = yield phantomjs.eval('myvalue')

        self.assertEqual(123, result)

        yield phantomjs.set('myvalue', 'abc')

        result = yield phantomjs.eval('myvalue')

        self.assertEqual('abc', result)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_events(self):
        phantomjs = PhantomJS()

        yield phantomjs.call('page.open', 'http://example.invalid')

        rpc_info = yield phantomjs.wait_page_event('load_finished')

        self.assertEqual('fail', rpc_info['status'])
