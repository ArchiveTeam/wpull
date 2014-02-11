# encoding=utf-8
import gettext
import logging
import os
import signal
import sys
import time
import tornado.ioloop

from wpull.app import Builder
from wpull.options import AppArgumentParser


_logger = logging.getLogger(__name__)
_ = gettext.gettext


def main():
    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()
    io_loop = tornado.ioloop.IOLoop.current()
    engine = Builder(args).build()
    status = {'graceful_called': False}

    def graceful_stop_handler(dummy1, dummy2):
        if status['graceful_called']:
            forceful_stop_handler(dummy1, dummy2)
            return

        status['graceful_called'] = True

        _logger.info(_('Stopping once all requests complete...'))
        _logger.info(_('Interrupt again to force stopping immediately.'))
        engine.stop()

    def forceful_stop_handler(dummy1, dummy2):
        _logger.info(_('Forcing immediate stop...'))
        engine.stop(force=True)

    signal.signal(signal.SIGINT, graceful_stop_handler)
    signal.signal(signal.SIGTERM, forceful_stop_handler)

    exit_code = io_loop.run_sync(engine)
    sys.exit(exit_code)


if __name__ == '__main__':
    if os.environ.get('RUN_PROFILE'):
        import cProfile
        cProfile.run('main()', 'stats-{0}.profile'.format(int(time.time())))
        # I suggest installing runsnakerun to view the profile file graphically
    else:
        main()
