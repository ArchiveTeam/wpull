# encoding=utf-8
import tornado.testing
from wpull.phantomjs import PhantomJS


DEFAULT_TIMEOUT = 30


class TestPhantomJS(tornado.testing.AsyncTestCase):
    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_rpc(self):
        phantomjs = PhantomJS()

        result = yield phantomjs.call('debug_echo', 'hello!')

        self.assertEqual('hello!', result)

        yield phantomjs.eval('var myvalue;')
        yield phantomjs.set('myvalue', 123)

        result = yield phantomjs.eval('myvalue')

        self.assertEqual(123, result)
