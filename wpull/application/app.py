# encoding=utf-8
'''Application main interface.'''
import enum
from collections import OrderedDict
import gettext
import logging
import platform
import signal

import asyncio

from typing import Iterable

from wpull.backport.logging import BraceMessage as __
from wpull.errors import ServerError, ExitStatus, ProtocolError, \
    SSLVerificationError, DNSNotFound, ConnectionRefused, NetworkError, \
    AuthenticationError
from wpull.application.hook import  HookStop
from wpull.pipeline.pipeline import Pipeline

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class ApplicationState(enum.Enum):
    ready = 'ready'
    running = 'running'
    stopping = 'stopping'
    stopped = 'stopped'


class Application(object):
    '''Default non-interactive application user interface.

    This class manages process signals and displaying warnings.
    '''
    ERROR_CODE_MAP = OrderedDict([
        (AuthenticationError, ExitStatus.authentication_failure),
        (ServerError, ExitStatus.server_error),
        (ProtocolError, ExitStatus.protocol_error),
        (SSLVerificationError, ExitStatus.ssl_verification_error),
        (DNSNotFound, ExitStatus.network_failure),
        (ConnectionRefused, ExitStatus.network_failure),
        (NetworkError, ExitStatus.network_failure),
        (OSError, ExitStatus.file_io_error),
        (IOError, ExitStatus.file_io_error),
        # ExitStatus.parse_error is handled by the ArgumentParse and is not
        # needed here.
        # Anything else is ExitStatus.generic_error.
    ])
    '''Mapping of error types to exit status.'''

    EXPECTED_EXCEPTIONS = (
        ServerError, ProtocolError,
        SSLVerificationError, DNSNotFound,
        ConnectionRefused, NetworkError,
        OSError, IOError,
        HookStop, StopIteration, SystemExit, KeyboardInterrupt,
    )
    '''Exception classes that are not crashes.'''

    def __init__(self, pipelines: Iterable[Pipeline]):
        super().__init__()
        self._pipelines = pipelines
        self._exit_code = 0
        self._current_pipeline = None
        self._state = ApplicationState.ready

        # self.register_hook('exit_status', 'finishing_statistics')

    # @property
    # def builder(self) -> Builder:
    #     '''The application builder.
    #     '''
    #     return self._builder

    def setup_signal_handlers(self):
        '''Setup Ctrl+C and SIGTERM handlers.'''
        if platform.system() == 'Windows':
            _logger.warning(_(
                'Graceful stopping with Unix signals is not supported '
                'on this OS.'
            ))
            return

        event_loop = asyncio.get_event_loop()
        graceful_called = False

        def graceful_stop_callback():
            nonlocal graceful_called

            if graceful_called:
                forceful_stop_callback()
                return

            graceful_called = True

            _logger.info(_('Stopping once all requests complete...'))
            _logger.info(_('Interrupt again to force stopping immediately.'))
            self.stop()

        def forceful_stop_callback():
            _logger.info(_('Forcing immediate stop...'))
            logging.raiseExceptions = False
            event_loop.stop()

        event_loop.add_signal_handler(signal.SIGINT, graceful_stop_callback)
        event_loop.add_signal_handler(signal.SIGTERM, forceful_stop_callback)

    def stop(self):
        if self._state == ApplicationState.running:
            _logger.debug('Application stopping')

            self._state = ApplicationState.stopping

            if self._current_pipeline:
                self._current_pipeline.stop()

    def run_sync(self):
        '''Run the application.

        This function is blocking.

        Returns:
            int: The exit status.
        '''
        return asyncio.get_event_loop().run_until_complete(self.run())

    @asyncio.coroutine
    def run(self):
        if self._state != ApplicationState.ready:
            raise RuntimeError('Application is not ready')

        self._state = ApplicationState.running

        for pipeline in self._pipelines:
            self._current_pipeline = pipeline

            if self._state == ApplicationState.stopping and pipeline.skippable:
                continue

            try:
                yield from pipeline.process()
            except Exception as error:
                if isinstance(error, StopIteration):
                    raise

                is_expected = isinstance(error, self.EXPECTED_EXCEPTIONS)
                show_traceback = not is_expected

                if show_traceback:
                    _logger.exception('Fatal exception.')
                else:
                    _logger.error('{}'.format(error))

                self._update_exit_code_from_error(error)

                if not is_expected:
                    self._print_crash_message()
                    self._print_report_bug_message()

                break

        self._current_pipeline = None
        self._state = ApplicationState.stopping

        if self._exit_code == ExitStatus.ssl_verification_error:
            self._print_ssl_error()

        # try:
        #     self._exit_code = self.call_hook('exit_status', self._exit_code)
        #     assert self._exit_code is not None
        # except HookDisconnected:
        #     pass

        _logger.info(__(_('Exiting with status {0}.'), self._exit_code))

        self._state = ApplicationState.stopped

        return self._exit_code

    def _update_exit_code_from_error(self, error):
        '''Set the exit code based on the error type.

        Args:
            error (:class:`Exception`): An exception instance.
        '''
        for error_type, exit_code in self.ERROR_CODE_MAP.items():
            if isinstance(error, error_type):
                self.update_exit_code(exit_code)
                break
        else:
            self.update_exit_code(ExitStatus.generic_error)

    def update_exit_code(self, code: int):
        '''Set the exit code if it is serious than before.

        Args:
            code: The exit code.
        '''
        if code:
            if self._exit_code:
                self._exit_code = min(self._exit_code, code)
            else:
                self._exit_code = code

    @classmethod
    def _print_ssl_error(cls):
        '''Print an invalid SSL certificate warning.'''
        _logger.info(_('A SSL certificate could not be verified.'))
        _logger.info(_('To ignore and proceed insecurely, '
                       'use ‘--no-check-certificate’.'))

    @classmethod
    def _print_crash_message(cls):
        '''Print crashed message.'''
        _logger.critical(_('Sorry, Wpull unexpectedly crashed.'))

    @classmethod
    def _print_report_bug_message(cls):
        '''Print report the bug message.'''
        _logger.critical(_(
            'Please report this problem to the authors at Wpull\'s '
            'issue tracker so it may be fixed. '
            'If you know how to program, maybe help us fix it? '
            'Thank you for helping us help you help us all.'
        ))