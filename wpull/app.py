# encoding=utf-8
'''Application main interface.'''
import gettext
import logging
import signal

import tornado.ioloop


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Application(object):
    '''Default non-interactive application user interface.

    This class manages process signals and displaying warnings.
    '''
    def __init__(self, builder):
        super().__init__()
        self._builder = builder
        self._io_loop = tornado.ioloop.IOLoop.current()

    @property
    def builder(self):
        '''The application builder.

        Returns:
            :class:`.builder.Builder`
        '''
        return self._builder

    def setup_signal_handlers(self):
        '''Setup Ctrl+C and SIGTERM handlers.'''

        status = {'graceful_called': False}

        def graceful_stop_handler(dummy1, dummy2):
            self._io_loop.add_callback_from_signal(graceful_stop_callback)

        def forceful_stop_handler(dummy1, dummy2):
            self._io_loop.add_callback_from_signal(forceful_stop_callback)

        def graceful_stop_callback():
            if status['graceful_called']:
                forceful_stop_callback()
                return

            status['graceful_called'] = True

            _logger.info(_('Stopping once all requests complete...'))
            _logger.info(_('Interrupt again to force stopping immediately.'))
            self._builder.factory['Engine'].stop()

        def forceful_stop_callback():
            _logger.info(_('Forcing immediate stop...'))
            self._builder.factory['Engine'].stop(force=True)

        signal.signal(signal.SIGINT, graceful_stop_handler)
        signal.signal(signal.SIGTERM, forceful_stop_handler)

    def run_sync(self):
        '''Run the application.

        This function is blocking.

        Returns:
            int: The exit status.
        '''
        return self._io_loop.run_sync(self._builder.factory['Engine'])
