import functools
import unittest

from tornado.platform.asyncio import BaseAsyncIOLoop
import trollius


# http://stackoverflow.com/q/23033939/1524507
class AsyncTestCase(unittest.TestCase):
    def setUp(self):
        self.event_loop = trollius.new_event_loop()
        self.event_loop.set_debug(True)
        trollius.set_event_loop(self.event_loop)

    def tearDown(self):
        self.event_loop.stop()
        self.event_loop.close()


def async_test(func=None, timeout=30):
    # tornado.testing
    def wrap(f):
        f = trollius.coroutine(f)

        @functools.wraps(f)
        def wrapper(self):
            return self.event_loop.run_until_complete(
                trollius.wait_for(f(self), timeout=timeout,
                                  loop=self.event_loop)
            )
        return wrapper

    if func is not None:
        # Used like:
        #     @gen_test
        #     def f(self):
        #         pass
        return wrap(func)
    else:
        # Used like @gen_test(timeout=10)
        return wrap


class TornadoAsyncIOLoop(BaseAsyncIOLoop):
    def initialize(self, event_loop):
        super().initialize(event_loop, close_loop=False)
