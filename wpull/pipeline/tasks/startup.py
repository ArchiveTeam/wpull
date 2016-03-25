import codecs
import gettext
import logging
import asyncio
import os
import socket
import ssl
import tempfile
import atexit
import sys

import itertools
import tornado.web
import tornado.httpserver

from wpull.application.options import LOG_QUIET, LOG_DEBUG
from wpull.application.options import LOG_VERY_QUIET, LOG_NO_VERBOSE, \
    LOG_VERBOSE
from wpull.backport.logging import BraceMessage as __
from wpull.database.sqltable import GenericSQLURLTable
from wpull.debug import DebugConsoleHandler
from wpull.pipeline.pipeline import ItemTask
import wpull.string
import wpull.url
import wpull.util
import wpull.warc
from wpull.pipline.app import AppSession, new_encoded_stream

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class LoggingSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._setup_logging(session.args)
        self._setup_console_logger(session, session.args,
                                   session.factory['Application'].get_stderr())
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


class ArgWarningTask(ItemTask[AppSession]):
    UNSAFE_OPTIONS = frozenset(['save_headers', 'no_iri', 'output_document',
                                'ignore_fatal_errors'])

    @asyncio.coroutine
    def process(self, session: AppSession):
        self._warn_unsafe_options(session.args)
        self._warn_silly_options(session.args)

    @classmethod
    def _warn_unsafe_options(cls, args):
        '''Print warnings about any enabled hazardous options.

        This function will print messages complaining about:

        * ``--save-headers``
        * ``--no-iri``
        * ``--output-document``
        * ``--ignore-fatal-errors``
        '''
        enabled_options = []

        for option_name in cls.UNSAFE_OPTIONS:
            if getattr(args, option_name):
                enabled_options.append(option_name)

        if enabled_options:
            _logger.warning(__(
                _('The following unsafe options are enabled: {list}.'),
                list=enabled_options
            ))
            _logger.warning(
                _('The use of unsafe options may lead to unexpected behavior '
                  'or file corruption.'))

        if not args.retr_symlinks:
            _logger.warning(
                _('The --retr-symlinks=off option is a security risk.')
            )

    @classmethod
    def _warn_silly_options(cls, args):
        '''Print warnings about any options that may be silly.'''
        if 'page-requisites' in args.span_hosts_allow \
                and not args.page_requisites:
            _logger.warning(
                _('Spanning hosts is allowed for page requisites, '
                  'but the page requisites option is not on.')
            )

        if 'linked-pages' in args.span_hosts_allow \
                and not args.recursive:
            _logger.warning(
                _('Spanning hosts is allowed for linked pages, '
                  'but the recursive option is not on.')
            )

        if args.warc_file and \
                (args.http_proxy or args.https_proxy):
            _logger.warning(_('WARC specifications do not handle proxies.'))

        if (args.password or args.ftp_password or
                args.http_password or args.proxy_password) and \
                args.warc_file:
            _logger.warning(
                _('Your password is recorded in the WARC file.'))


class DebugConsoleSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        if session.args.debug_console_port is None:
            return

        application = tornado.web.Application(
            [(r'/', DebugConsoleHandler)],
            builder=self
        )
        sock = socket.socket()
        sock.bind(('localhost', session.args.debug_console_port))
        sock.setblocking(0)
        sock.listen(1)
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.add_socket(sock)

        _logger.warning(__(
            _('Opened a debug console at localhost:{port}.'),
            port=sock.getsockname()[1]
        ))

        atexit.register(sock.close)


class DatabaseSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        if session.args.database_uri:
            session.factory.class_map[
                'URLTableImplementation'] = GenericSQLURLTable
            url_table_impl = session.factory.new(
                'URLTableImplementation', session.args.database_uri)
        else:
            url_table_impl = session.factory.new(
                'URLTableImplementation', path=session.args.database)

        url_table = session.factory.new('URLTable', url_table_impl)


class InputURLTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        url_table = session.factory['URLTable']

        for batch in wpull.util.grouper(self._read_input_urls(session), 1000):
            url_table.add_many(url_info.url for url_info in batch if url_info)
            # TODO: attach hook for notifying progress

            # TODO: raise on error if no urls
            # urls = (line.strip() for line in input_file if line.strip())
            #
            # if not urls:
            #     raise ValueError(_('No URLs found in input file.'))
            #
            # return urls

    @classmethod
    def _read_input_urls(cls, session: AppSession, default_scheme='http'):
        '''Read the URLs provided by the user.'''

        url_string_iter = session.args.urls or ()
        url_rewriter = session.factory['URLRewriter']

        if session.args.input_file:
            if session.args.force_html:
                lines = cls._input_file_as_html_links(session)
            else:
                lines = cls._input_file_as_lines(session)

            url_string_iter = itertools.chain(url_string_iter, lines)

        base_url = session.args.base

        for url_string in url_string_iter:
            _logger.debug(__('Parsing URL {0}', url_string))

            if base_url:
                url_string = wpull.url.urljoin(base_url, url_string)

            url_info = wpull.url.URLInfo.parse(
                url_string, default_scheme=default_scheme)

            _logger.debug(__('Parsed URL {0}', url_info))

            if url_rewriter:
                # TODO: this logic should be a hook
                url_info = url_rewriter.rewrite(url_info)
                _logger.debug(__('Rewritten URL {0}', url_info))

            yield url_info

    @classmethod
    def _input_file_as_lines(cls, session: AppSession):
        '''Read lines from input file and return them.'''
        if session.args.input_file == sys.stdin:
            input_file = session.args.input_file
        else:
            reader = codecs.getreader(session.args.local_encoding or 'utf-8')
            input_file = reader(session.args.input_file)

        return input_file

    @classmethod
    def _input_file_as_html_links(cls, session: AppSession):
        '''Read input file as HTML and return the links.'''
        scrape_result = session.factory['HTMLScraper'].scrape_file(
            session.args.input_file,
            encoding=session.args.local_encoding or 'utf-8'
        )

        for context in scrape_result.link_contexts
            yield context.link

class WARCVisitsTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        '''Populate the visits from the CDX into the URL table.'''
        iterable = wpull.warc.read_cdx(
            session.args.warc_dedup,
            encoding=session.args.local_encoding or 'utf-8'
        )

        missing_url_msg = _('The URL ("a") is missing from the CDX file.')
        missing_id_msg = _('The record ID ("u") is missing from the CDX file.')
        missing_checksum_msg = \
            _('The SHA1 checksum ("k") is missing from the CDX file.')

        counter = 0

        def visits():
            nonlocal counter
            checked_fields = False

            for record in iterable:
                if not checked_fields:
                    if 'a' not in record:
                        raise ValueError(missing_url_msg)
                    if 'u' not in record:
                        raise ValueError(missing_id_msg)
                    if 'k' not in record:
                        raise ValueError(missing_checksum_msg)

                    checked_fields = True

                yield record['a'], record['u'], record['k']
                counter += 1

        url_table = session.factory['URLTable']
        url_table.add_visits(visits())

        _logger.info(__(
            gettext.ngettext(
                'Loaded {num} record from CDX file.',
                'Loaded {num} records from CDX file.',
                counter
            ),
            num=counter
        ))


class SSLContextTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        session.ssl_context = self._build_ssl_context(session)

    @classmethod
    def _build_ssl_context(cls, session: AppSession) -> ssl.SSLContext:
        '''Create the SSL options.

        The options must be accepted by the `ssl` module.
        '''
        args = session.args

        # Logic is based on tornado.netutil.ssl_options_to_context
        ssl_context = ssl.SSLContext(args.secure_protocol)

        if args.check_certificate:
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            cls._load_ca_certs(session)
            ssl_context.load_verify_locations(session.ca_certs_filename)
        else:
            ssl_context.verify_mode = ssl.CERT_NONE

        if args.strong_crypto:
            ssl_context.options |= ssl.OP_NO_SSLv2
            ssl_context.options |= ssl.OP_NO_SSLv3  # POODLE

            if hasattr(ssl, 'OP_NO_COMPRESSION'):
                ssl_context.options |= ssl.OP_NO_COMPRESSION  # CRIME
            else:
                _logger.warning(_('Unable to disable TLS compression.'))

        if args.certificate:
            ssl_context.load_cert_chain(args.certificate, args.private_key)

        if args.edg_file:
            ssl.RAND_egd(args.edg_file)

        if args.random_file:
            with open(args.random_file, 'rb') as in_file:
                # Use 16KB because Wget
                ssl.RAND_add(in_file.read(15360), 0.0)

        return ssl_context

    @classmethod
    def _load_ca_certs(cls, session: AppSession, clean: bool=True):
        '''Load the Certificate Authority certificates.
        '''
        args = session.args

        if session.ca_certs_filename:
            return session.ca_certs_filename

        certs = set()

        if args.use_internal_ca_certs:
            pem_filename = os.path.join(
                os.path.dirname(__file__), 'cert', 'ca-bundle.pem'
            )
            certs.update(cls._read_pem_file(pem_filename, from_package=True))

        if args.ca_directory:
            if os.path.isdir(args.ca_directory):
                for filename in os.listdir(args.ca_directory):
                    if os.path.isfile(filename):
                        certs.update(cls._read_pem_file(filename))
            else:
                _logger.warning(__(
                    _('Certificate directory {path} does not exist.'),
                    path=args.ca_directory
                ))

        if args.ca_certificate:
            if os.path.isfile(args.ca_certificate):
                certs.update(cls._read_pem_file(args.ca_certificate))
            else:
                _logger.warning(__(
                    _('Certificate file {path} does not exist.'),
                    path=args.ca_certificate
                ))

        session.ca_certs_filename = certs_filename = tempfile.mkstemp(
            suffix='.pem', prefix='tmp-wpull-')[1]

        def clean_certs_file():
            os.remove(certs_filename)

        if clean:
            atexit.register(clean_certs_file)

        with open(certs_filename, 'w+b') as certs_file:
            for cert in certs:
                certs_file.write(cert)

        _logger.debug('CA certs loaded.')

    @classmethod
    def _read_pem_file(cls, filename, from_package=False):
        '''Read the PEM file.

        Returns:
            iterable: An iterable of certificates. The certificate data
            is :class:`byte`.
        '''
        _logger.debug('Reading PEM {0}.'.format(filename))

        if from_package:
            return wpull.util.filter_pem(wpull.util.get_package_data(filename))

        with open(filename, 'rb') as in_file:
            return wpull.util.filter_pem(in_file.read())



