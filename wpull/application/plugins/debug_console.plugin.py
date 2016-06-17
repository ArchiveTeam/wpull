import gettext
import logging
import socket
import atexit

import tornado.web
import tornado.httpserver

from wpull.application.plugin import WpullPlugin
from wpull.backport.logging import BraceMessage as __
from wpull.debug import DebugConsoleHandler

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class DebugConsolePlugin(WpullPlugin):
    def activate(self):
        super().activate()
        if self.app_session.args.debug_console_port is None:
            return

        application = tornado.web.Application(
            [(r'/', DebugConsoleHandler)],
            builder=self
        )
        sock = socket.socket()
        sock.bind(('localhost', self.app_session.args.debug_console_port))
        sock.setblocking(0)
        sock.listen(1)
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.add_socket(sock)

        _logger.warning(__(
            _('Opened a debug console at localhost:{port}.'),
            port=sock.getsockname()[1]
        ))

        atexit.register(sock.close)
