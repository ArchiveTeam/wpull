import logging

import asyncio

from wpull.application.options import LOG_VERY_QUIET, LOG_QUIET, LOG_NO_VERBOSE, LOG_VERBOSE, LOG_DEBUG
from wpull.pipeline.app import AppSession, new_encoded_stream
from wpull.pipeline.pipeline import ItemTask


class LoggingSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._setup_logging(session.args)
        self._setup_console_logger(session, session.args, session.stderr)
        self._setup_file_logger(session, session.args)

    @classmethod
    def _setup_logging(cls, args):
        '''Set up the root logger if needed.

        The root logger is set the appropriate level so the file and WARC logs
        work correctly.
        '''
        assert (
            logging.CRITICAL >
            logging.ERROR >
            logging.WARNING >
            logging.INFO >
            logging.DEBUG >
            logging.NOTSET
        )
        assert (
            LOG_VERY_QUIET >
            LOG_QUIET >
            LOG_NO_VERBOSE >
            LOG_VERBOSE >
            LOG_DEBUG
        )
        assert args.verbosity

        root_logger = logging.getLogger()
        current_level = root_logger.getEffectiveLevel()
        min_level = LOG_VERY_QUIET

        if args.verbosity == LOG_QUIET:
            min_level = logging.ERROR

        if args.verbosity in (LOG_NO_VERBOSE, LOG_VERBOSE) \
                or args.warc_file \
                or args.output_file or args.append_output:
            min_level = logging.INFO

        if args.verbosity == LOG_DEBUG:
            min_level = logging.DEBUG

        if current_level > min_level:
            root_logger.setLevel(min_level)
            root_logger.debug(
                'Wpull needs the root logger level set to {0}.'
                    .format(min_level)
            )

        if current_level <= logging.INFO:
            logging.captureWarnings(True)

    @classmethod
    def _setup_console_logger(cls, session: AppSession, args, stderr):
        '''Set up the console logger.

        A handler and with a formatter is added to the root logger.
        '''
        stream = new_encoded_stream(args, stderr)

        logger = logging.getLogger()
        session.console_log_handler = handler = logging.StreamHandler(stream)

        formatter = logging.Formatter('%(levelname)s %(message)s')
        log_filter = logging.Filter('wpull')

        handler.setFormatter(formatter)
        handler.setLevel(args.verbosity or logging.INFO)
        handler.addFilter(log_filter)
        logger.addHandler(handler)

    @classmethod
    def _setup_file_logger(cls, session: AppSession, args):
        '''Set up the file message logger.

        A file log handler and with a formatter is added to the root logger.
        '''
        if not (args.output_file or args.append_output):
            return

        logger = logging.getLogger()

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        if args.output_file:
            filename = args.output_file
            mode = 'w'
        else:
            filename = args.append_output
            mode = 'a'

        session.file_log_handler = handler = logging.FileHandler(
            filename, mode, encoding='utf-8')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if args.verbosity == logging.DEBUG:
            handler.setLevel(logging.DEBUG)
        else:
            handler.setLevel(logging.INFO)


class LoggingShutdownTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._close_console_logger(session)
        self._close_file_logger(session)

    @classmethod
    def _close_console_logger(cls, session: AppSession):
        if session.console_log_handler:
            logger = logging.getLogger()
            logger.removeHandler(session.console_log_handler)
            session.console_log_handler = None

    @classmethod
    def _close_file_logger(cls, session: AppSession):
        if session.file_log_handler:
            logger = logging.getLogger()
            logger.removeHandler(session.file_log_handler)
            session.file_log_handler = None
