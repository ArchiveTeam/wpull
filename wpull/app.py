# encoding=utf-8
'''Application main interface.'''
import datetime
import gettext
import logging
import signal

import tornado.ioloop

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ServerError, ExitStatus, ProtocolError, \
    SSLVerficationError, DNSNotFound, ConnectionRefused, NetworkError
from wpull.hook import HookableMixin, HookDisconnected
import wpull.string


try:
    from collections import OrderedDict
except ImportError:
    from wpull.backport.collections import OrderedDict


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Application(HookableMixin):
    '''Default non-interactive application user interface.

    This class manages process signals and displaying warnings.
    '''
    ERROR_CODE_MAP = OrderedDict([
        (ServerError, ExitStatus.server_error),
        (ProtocolError, ExitStatus.protocol_error),
        (SSLVerficationError, ExitStatus.ssl_verification_error),
        (DNSNotFound, ExitStatus.network_failure),
        (ConnectionRefused, ExitStatus.network_failure),
        (NetworkError, ExitStatus.network_failure),
        (OSError, ExitStatus.file_io_error),
        (IOError, ExitStatus.file_io_error),
        (ValueError, ExitStatus.parser_error),
    ])
    '''Mapping of error types to exit status.'''

    def __init__(self, builder):
        super().__init__()
        self._builder = builder
        self._io_loop = tornado.ioloop.IOLoop.current()
        self._exit_code = 0
        self._statistics = None
        self.stop_observer = wpull.observer.Observer()

        self.register_hook('exit_status', 'finishing_statistics')

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
        return self._io_loop.run_sync(self.run)

    @tornado.gen.coroutine
    def run(self):
        self._statistics = self._builder.factory['Statistics']
        self._statistics.start()

        try:
            yield self._builder.factory['Engine']()
        except Exception as error:
            _logger.exception('Fatal exception.')
            self._update_exit_code_from_error(error)

        self._compute_exit_code_from_stats()

        if self._exit_code == ExitStatus.ssl_verification_error:
            self._print_ssl_error()

        self._statistics.stop()

        try:
            self._exit_code = self.call_hook('exit_status', self._exit_code)
            assert self._exit_code is not None
        except HookDisconnected:
            pass

        try:
            self.call_hook(
                'finishing_statistics',
                self._statistics.start_time, self._statistics.stop_time,
                self._statistics.files, self._statistics.size
            )
        except HookDisconnected:
            pass

        self._print_stats()
        self.stop_observer.notify()

        raise tornado.gen.Return(self._exit_code)

    def _update_exit_code_from_error(self, error):
        '''Set the exit code based on the error type.

        Args:
            error (:class:`Exception`): An exception instance.
        '''
        for error_type, exit_code in self.ERROR_CODE_MAP.items():
            if isinstance(error, error_type):
                self._update_exit_code(exit_code)
                break
        else:
            self._update_exit_code(ExitStatus.generic_error)

    def _update_exit_code(self, code):
        '''Set the exit code if it is serious than before.

        Args:
            code (int): The exit code.
        '''
        if code:
            if self._exit_code:
                self._exit_code = min(self._exit_code, code)
            else:
                self._exit_code = code

    def _compute_exit_code_from_stats(self):
        '''Set the current exit code based on the Statistics.'''
        for error_type in self._statistics.errors:
            exit_code = self.ERROR_CODE_MAP.get(error_type)
            if exit_code:
                self._update_exit_code(exit_code)

    def _print_stats(self):
        '''Log the final statistics to the user.'''
        stats = self._statistics
        time_length = datetime.timedelta(
            seconds=int(stats.stop_time - stats.start_time)
        )
        file_size = wpull.string.format_size(stats.size)

        if stats.bandwidth_meter.num_samples:
            speed_size_str = wpull.string.format_size(
                stats.bandwidth_meter.speed()
            )
        else:
            speed_size_str = _('-- B')

        _logger.info(_('FINISHED.'))
        _logger.info(__(
            _(
                'Duration: {preformatted_timedelta}. '
                'Speed: {preformatted_speed_size}/s.'
            ),
            preformatted_timedelta=time_length,
            preformatted_speed_size=speed_size_str,
        ))
        _logger.info(__(
            gettext.ngettext(
                'Downloaded: {num_files} file, {preformatted_file_size}.',
                'Downloaded: {num_files} files, {preformatted_file_size}.',
                stats.files
            ),
            num_files=stats.files,
            preformatted_file_size=file_size
        ))

        if stats.is_quota_exceeded:
            _logger.info(_('Download quota exceeded.'))

        _logger.info(__(_('Exiting with status {0}.'), self._exit_code))

    def _print_ssl_error(self):
        '''Print an invalid SSL certificate warning.'''
        _logger.info(_('A SSL certificate could not be verified.'))
        _logger.info(_('To ignore and proceed insecurely, '
                       'use ‘--no-check-certificate’.'))
