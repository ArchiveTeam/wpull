# encoding=utf-8
import email.utils
import hashlib
import http.client
import logging
import os.path
import time

from tornado.testing import AsyncHTTPTestCase
from tornado.web import HTTPError
import tornado.web

from wpull.testing.async import AsyncTestCase


_logger = logging.getLogger(__name__)


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_cookie('hi', 'hello', expires_days=2)
        page = self.render_string('index.html')
        self.write(page[:10])
        self.flush()
        self.add_header('Animal', 'dolphin')
        self.write(page[10:])


class BlogHandler(tornado.web.RequestHandler):
    def initialize(self):
        if not hasattr(self.application, 'counter'):
            self.application.counter = 0

    def get(self):
        self.application.counter += 1
        page_num = int(self.get_argument('page', 1))
        if 1 <= page_num <= 5:
            if self.application.counter % 2 == 0:
                raise HTTPError(500)
            self.render('blog.html', page_num=page_num)
        else:
            raise HTTPError(404)


class InfiniteHandler(tornado.web.RequestHandler):
    def get(self):
        page_num = int(self.get_argument('page', 1))
        self.render('infinite.html', page_num=page_num)


class PostHandler(tornado.web.RequestHandler):
    def post(self):
        self.get_argument('text')
        self.write(b'OK')


class CookieHandler(tornado.web.RequestHandler):
    def get(self):
        cookie_value = self.get_cookie('test')
        _logger.debug('Got cookie value {0}'.format(cookie_value))

        if cookie_value == 'no':
            self.set_cookie('test', 'yes', expires_days=2)
            self.write(b'OK')
        else:
            raise HTTPError(400)


class RedirectHandler(tornado.web.RequestHandler):
    def get(self):
        where = self.get_argument('where', None)

        if where == 'diff-host':
            port = self.get_argument('port')
            self.redirect('http://somewhereelse.invalid:{0}'.format(port))
        elif self.get_argument('code', None):
            self.redirect('/', status=int(self.get_argument('code')))
        else:
            self.redirect('/', status=301)


class LastModifiedHandler(tornado.web.RequestHandler):
    def get(self):
        if 'If-Modified-Since' in self.request.headers:
            time_tuple = email.utils.parsedate_tz(
                self.request.headers['If-Modified-Since'])
            timestamp = time.mktime(time_tuple[:9])

            if timestamp < 634521600:
                self.set_status(http.client.NOT_MODIFIED)
                return

        self.write('HELLO')


class AlwaysErrorHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_status(500, 'Dragon In Data Center')
        self.write('Error')


class SpanHostsHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('span_hosts.html', port=self.get_argument('port'))


class BigPayloadHandler(tornado.web.RequestHandler):
    def get(self):
        hash_obj = hashlib.sha1(b'foxfoxfox')

        for counter in range(10000):
            data = hash_obj.digest()
            self.write(data)
            hash_obj.update(data)

            if counter % 133 == 0:
                self.flush()

        data = hash_obj.digest()
        self.write(data)
        self.flush()


class DirOrFileHandle(tornado.web.RequestHandler):
    def get(self):
        self.write(b'OH-NO')


class SomePageHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(b'Hello world!')


class BasicAuthHandler(tornado.web.RequestHandler):
    def get(self):
        _logger.debug('Authorization: %s', self.request.headers.get('Authorization'))
        if self.request.headers.get('Authorization') == 'Basic cm9vdDpzbWF1Zw==':
            self.write(b'Welcome. The Krabby Patty Secret formula is:')
        else:
            raise HTTPError(401)


class GoodApp(tornado.web.Application):
    def __init__(self):
        tornado.web.Application.__init__(self, [
            (r'/', IndexHandler),
            (r'/blog/?', BlogHandler),
            (r'/infinite/', InfiniteHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler),
            (r'/post/', PostHandler),
            (r'/cookie', CookieHandler),
            (r'/redirect', RedirectHandler),
            (r'/lastmod', LastModifiedHandler),
            (r'/always_error', AlwaysErrorHandler),
            (r'/span_hosts', SpanHostsHandler),
            (r'/big_payload', BigPayloadHandler),
            (r'/dir_or_file', DirOrFileHandle),
            (r'/dir_or_file/', DirOrFileHandle),
            (r'/mordor', SomePageHandler),
            (r'/some_page/', SomePageHandler),
            (r'/some_page', tornado.web.RedirectHandler,
             {'url': '/some_page/'}),
            (r'/basic_auth', BasicAuthHandler),
        ],
            template_path=os.path.join(os.path.dirname(__file__),
                                       'templates'),
            static_path=os.path.join(os.path.dirname(__file__),
                                     'static'),
            serve_traceback=True,
            gzip=True,
        )


class GoodAppTestCase(AsyncTestCase, AsyncHTTPTestCase):
    def get_new_ioloop(self):
        tornado.ioloop.IOLoop.configure(
            'wpull.testing.async.TornadoAsyncIOLoop',
            event_loop=self.event_loop)
        ioloop = tornado.ioloop.IOLoop()
        return ioloop

    def setUp(self):
        AsyncTestCase.setUp(self)
        AsyncHTTPTestCase.setUp(self)
        # Wait for the app to start up properly (for good luck).
        time.sleep(0.5)

    def get_app(self):
        return GoodApp()

if __name__ == '__main__':
    app = GoodApp()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
