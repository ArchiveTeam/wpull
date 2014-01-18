# encoding=utf-8
import os.path
import time
from tornado.testing import AsyncHTTPTestCase
from tornado.web import HTTPError
import tornado.web


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
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


class GoodApp(tornado.web.Application):
    def __init__(self):
        tornado.web.Application.__init__(self, [
                (r'/', IndexHandler),
                (r'/blog/?', BlogHandler),
                (r'/static/(.*)', tornado.web.StaticFileHandler),
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
