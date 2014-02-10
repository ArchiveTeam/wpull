# encoding=utf-8
import logging
import os.path
import time
from tornado.testing import AsyncHTTPTestCase
from tornado.web import HTTPError
import tornado.web


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
            self.redirect('http://somewhereelse.invalid')
        else:
            self.redirect('/', status=301)


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
            ],
            template_path=os.path.join(os.path.dirname(__file__),
                'templates'),
            static_path=os.path.join(os.path.dirname(__file__),
                'static'),
            serve_traceback=True,
        )


class GoodAppTestCase(AsyncHTTPTestCase):
    def setUp(self):
        AsyncHTTPTestCase.setUp(self)
        # Wait for the app to start up properly (for good luck).
        time.sleep(0.5)

    def get_app(self):
        return GoodApp()

if __name__ == '__main__':
    app = GoodApp()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
