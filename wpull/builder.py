# encoding=utf-8
'''Application support.'''
from http.cookiejar import CookieJar
import atexit
import codecs
import functools
import gettext
import itertools
import logging
import os.path
import socket
import ssl
import sys
import tempfile

import tornado.testing
import tornado.netutil
import tornado.web
import trollius

from wpull.app import Application
from wpull.backport.logging import BraceMessage as __
from wpull.bandwidth import BandwidthLimiter
from wpull.connection import Connection, ConnectionPool, SSLConnection
from wpull.converter import BatchDocumentConverter
from wpull.cookie import DeFactoCookiePolicy, RelaxedMozillaCookieJar
from wpull.coprocessor.proxy import ProxyCoprocessor
from wpull.coprocessor.youtubedl import YoutubeDlCoprocessor
from wpull.database.sqltable import URLTable as SQLURLTable, GenericSQLURLTable
from wpull.database.wrap import URLTableHookWrapper
from wpull.debug import DebugConsoleHandler
from wpull.dns import Resolver, PythonResolver
from wpull.engine import Engine
from wpull.factory import Factory
from wpull.ftp.client import Client as FTPClient
from wpull.hook import HookEnvironment, PluginEnvironment
from wpull.http.client import Client as HTTPClient
from wpull.http.proxy import ProxyAdapter
from wpull.http.redirect import RedirectTracker
from wpull.http.request import Request
from wpull.http.robots import RobotsTxtChecker
from wpull.http.stream import Stream as HTTPStream
from wpull.http.web import WebClient
from wpull.namevalue import NameValueRecord
from wpull.driver.phantomjs import PhantomJSDriver
from wpull.options import LOG_QUIET, LOG_VERY_QUIET, LOG_NO_VERBOSE, LOG_VERBOSE, \
    LOG_DEBUG
from wpull.processor.delegate import DelegateProcessor
from wpull.processor.ftp import FTPProcessor, FTPProcessorFetchParams, \
    FTPProcessorInstances
from wpull.processor.rule import FetchRule, ResultRule, ProcessingRule
from wpull.coprocessor.phantomjs import PhantomJSCoprocessor, PhantomJSParams
from wpull.processor.web import WebProcessor, WebProcessorFetchParams, \
    WebProcessorInstances
from wpull.proxy import HTTPProxyServer
from wpull.recorder.demux import DemuxRecorder
from wpull.recorder.document import OutputDocumentRecorder
from wpull.recorder.printing import PrintServerResponseRecorder
from wpull.recorder.progress import ProgressRecorder
from wpull.recorder.warc import WARCRecorder, WARCRecorderParams
from wpull.robotstxt import RobotsTxtPool
from wpull.scraper.base import DemuxDocumentScraper
from wpull.scraper.css import CSSScraper
from wpull.scraper.html import HTMLScraper, ElementWalker
from wpull.scraper.javascript import JavaScriptScraper
from wpull.scraper.sitemap import SitemapScraper
from wpull.stats import Statistics
from wpull.url import URLInfo
from wpull.urlfilter import (DemuxURLFilter, HTTPSOnlyFilter, SchemeFilter,
                             BackwardDomainFilter, HostnameFilter, TriesFilter,
                             RecursiveFilter, LevelFilter,
                             SpanHostsFilter, RegexFilter, DirectoryFilter,
                             BackwardFilenameFilter, ParentFilter,
                             FollowFTPFilter)
from wpull.urlrewrite import URLRewriter
from wpull.util import ASCIIStreamWriter
from wpull.waiter import LinearWaiter
from wpull.wrapper import CookieJarWrapper
from wpull.writer import (PathNamer, NullWriter, OverwriteFileWriter,
                          IgnoreFileWriter, TimestampingFileWriter,
                          AntiClobberFileWriter)
import wpull.version


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Builder(object):
    '''Application builder.

    Args:
        args: Options from :class:`argparse.ArgumentParser`
    '''
    UNSAFE_OPTIONS = frozenset(['save_headers', 'no_iri', 'output_document',
                                'ignore_fatal_errors'])

    def __init__(self, args, unit_test=False):
        self.default_user_agent = 'Wpull/{0} (gzip)'.format(
            wpull.version.__version__)
        self._args = args
        self._factory = Factory({
            'Application': Application,
            'BatchDocumentConverter': BatchDocumentConverter,
            'BandwidthLimiter': BandwidthLimiter,
            'HTTPClient': HTTPClient,
            'CookieJar': CookieJar,
            'CookieJarWrapper': CookieJarWrapper,
            'CookiePolicy': DeFactoCookiePolicy,
            'ConnectionPool': ConnectionPool,
            'CSSScraper': CSSScraper,
            'DemuxDocumentScraper': DemuxDocumentScraper,
            'DemuxRecorder': DemuxRecorder,
            'DemuxURLFilter': DemuxURLFilter,
            'FTPProcessor': FTPProcessor,
            'Engine': Engine,
            'ElementWalker': ElementWalker,
            'FetchRule': FetchRule,
            'FileWriter': NullWriter,
            'FTPClient': FTPClient,
            'FTPProcessorFetchParams': FTPProcessorFetchParams,
            'FTPProcessorInstances': FTPProcessorInstances,
            'HTTPProxyServer': HTTPProxyServer,
            'HTMLParser': NotImplemented,
            'HTMLScraper': HTMLScraper,
            'JavaScriptScraper': JavaScriptScraper,
            'OutputDocumentRecorder': OutputDocumentRecorder,
            'PathNamer': PathNamer,
            'PhantomJSDriver': PhantomJSDriver,
            'PhantomJSCoprocessor': PhantomJSCoprocessor,
            'PrintServerResponseRecorder': PrintServerResponseRecorder,
            'ProcessingRule': ProcessingRule,
            'Processor': DelegateProcessor,
            'ProxyAdapter': ProxyAdapter,
            'ProxyCoprocessor': ProxyCoprocessor,
            'ProgressRecorder': ProgressRecorder,
            'RedirectTracker': RedirectTracker,
            'Request': Request,
            'Resolver': NotImplemented,
            'ResultRule': ResultRule,
            'RobotsTxtChecker': RobotsTxtChecker,
            'RobotsTxtPool': RobotsTxtPool,
            'SitemapScraper': SitemapScraper,
            'Statistics': Statistics,
            'URLInfo': URLInfo,
            'URLTable': URLTableHookWrapper,
            'URLTableImplementation': SQLURLTable,
            'URLRewriter': URLRewriter,
            'Waiter': LinearWaiter,
            'WARCRecorder': WARCRecorder,
            'WebClient': WebClient,
            'WebProcessor': WebProcessor,
            'WebProcessorFetchParams': WebProcessorFetchParams,
            'WebProcessorInstances': WebProcessorInstances,
            'YoutubeDlCoprocessor': YoutubeDlCoprocessor,
        })
        self._url_infos = None
        self._ca_certs_file = None
        self._file_log_handler = None
        self._console_log_handler = None
        self._unit_test = unit_test

    @property
    def factory(self):
        '''Return the Factory.

        Returns:
            Factory: An :class:`.factory.Factory` instance.
        '''
        return self._factory

    def build(self):
        '''Put the application together.

        Returns:
            Application: An instance of :class:`.app.Application`.
        '''
        self._setup_logging()

        if self._args.plugin_script:
            self._initialize_plugin()

        self._factory.new('Application', self)

        self._build_html_parser()
        self._setup_console_logger()
        self._setup_file_logger()
        self._setup_debug_console()

        self._build_demux_document_scraper()
        self._url_infos = tuple(self._build_input_urls())

        statistics = self._factory.new('Statistics')
        statistics.quota = self._args.quota
        statistics.required_url_infos.update(self._url_infos)

        url_table = self._build_url_table()
        processor = self._build_processor()

        self._factory.new(
            'Engine',
            url_table,
            processor,
            statistics,
            concurrent=self._args.concurrent,
            ignore_exceptions=self._args.ignore_fatal_errors
        )
        self._build_document_converter()

        self._setup_file_logger_close(self.factory['Application'])
        self._setup_console_logger_close(self.factory['Application'])

        self._install_script_hooks()
        self._warn_unsafe_options()
        self._warn_silly_options()

        url_table.add_many(
            [{'url': url_info.url} for url_info in self._url_infos]
        )

        return self._factory['Application']

    def build_and_run(self):
        '''Build and run the application.

        Returns:
            int: The exit status.
        '''
        app = self.build()
        exit_code = app.run_sync()
        return exit_code

    def _initialize_plugin(self):
        '''Load the plugin script.'''
        filename = self._args.plugin_script
        _logger.info(__(
            _('Using Python hook script {filename}.'),
            filename=filename
        ))

        plugin_environment = PluginEnvironment(
            self._factory, self, self._args.plugin_args
        )

        with open(filename, 'rb') as in_file:
            code = compile(in_file.read(), filename, 'exec')
            context = {'wpull_plugin': plugin_environment}
            exec(code, context, context)

    def _new_encoded_stream(self, stream):
        '''Return a stream writer.'''
        if self._args.ascii_print:
            return ASCIIStreamWriter(stream)
        else:
            return stream

    def _setup_logging(self):
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
        assert self._args.verbosity

        root_logger = logging.getLogger()
        current_level = root_logger.getEffectiveLevel()
        min_level = LOG_VERY_QUIET

        if self._args.verbosity == LOG_QUIET:
            min_level = logging.ERROR

        if self._args.verbosity in (LOG_NO_VERBOSE, LOG_VERBOSE) \
                or self._args.warc_file \
                or self._args.output_file or self._args.append_output:
            min_level = logging.INFO

        if self._args.verbosity == LOG_DEBUG:
            min_level = logging.DEBUG

        if current_level > min_level:
            root_logger.setLevel(min_level)
            root_logger.debug(
                'Wpull needs the root logger level set to {0}.'
                .format(min_level)
            )

        if current_level <= logging.INFO:
            logging.captureWarnings(True)

    def _setup_console_logger(self):
        '''Set up the console logger.

        A handler and with a formatter is added to the root logger.
        '''
        stream = self._new_encoded_stream(self._get_stderr())

        logger = logging.getLogger()
        self._console_log_handler = handler = logging.StreamHandler(stream)

        formatter = logging.Formatter('%(levelname)s %(message)s')
        log_filter = logging.Filter('wpull')

        handler.setFormatter(formatter)
        handler.setLevel(self._args.verbosity or logging.INFO)
        handler.addFilter(log_filter)
        logger.addHandler(handler)

    def _setup_console_logger_close(self, app):
        '''Add routine to remove log handler when the application stops.'''
        def remove_handler():
            logger = logging.getLogger()
            logger.removeHandler(self._console_log_handler)
            self._console_log_handler = None

        if self._console_log_handler:
            app.stop_observer.add(remove_handler)

    def _setup_file_logger(self):
        '''Set up the file message logger.

        A file log handler and with a formatter is added to the root logger.
        '''
        args = self._args

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

        self._file_log_handler = handler = logging.FileHandler(
            filename, mode, encoding='utf-8')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if args.verbosity == logging.DEBUG:
            handler.setLevel(logging.DEBUG)
        else:
            handler.setLevel(logging.INFO)

    def _setup_file_logger_close(self, app):
        '''Add routine that removes the file log handler when the app stops.
        '''
        def remove_handler():
            logger = logging.getLogger()
            logger.removeHandler(self._file_log_handler)
            self._file_log_handler = None

        if self._file_log_handler:
            app.stop_observer.add(remove_handler)

    def _install_script_hooks(self):
        '''Set up the scripts if any.'''
        if self._args.python_script:
            self._install_python_script(self._args.python_script)
        elif self._args.lua_script:
            self._install_lua_script(self._args.lua_script)

    def _install_python_script(self, filename):
        '''Load the Python script into an environment.'''
        _logger.info(__(_('Using Python hook script {filename}.'),
                        filename=filename))

        hook_environment = HookEnvironment(self._factory)

        hook_environment.connect_hooks()

        with open(filename, 'rb') as in_file:
            code = compile(in_file.read(), filename, 'exec')
            context = {'wpull_hook': hook_environment}
            exec(code, context, context)

    def _install_lua_script(self, filename):
        '''Load the Lua script into an environment.'''
        _logger.info(__(_('Using Lua hook script {filename}.'),
                        filename=filename))

        hook_environment = HookEnvironment(self._factory)

        hook_environment.connect_hooks()

        adapter_filename = os.path.join(
            os.path.dirname(__file__), '_luahook.py')

        with open(adapter_filename, 'rb') as in_file:
            code = compile(in_file.read(), filename, 'exec')
            context = {'wpull_hook': hook_environment}
            exec(code, context, context)
            context['install'](filename)

    def _setup_debug_console(self):
        if self._args.debug_console_port is None:
            return

        application = tornado.web.Application(
            [(r'/', DebugConsoleHandler)],
            builder=self
        )
        sock = socket.socket()
        sock.bind(('localhost', self._args.debug_console_port))
        sock.setblocking(0)
        sock.listen(1)
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.add_socket(sock)

        _logger.warning(__(
            _('Opened a debug console at localhost:{port}.'),
            port=sock.getsockname()[1]
        ))

        atexit.register(sock.close)

    def _build_input_urls(self, default_scheme='http'):
        '''Read the URLs provided by the user.'''

        url_string_iter = self._args.urls or ()
        url_rewriter = self._build_url_rewriter()

        if self._args.input_file:
            if self._args.force_html:
                urls = self._read_input_file_as_html()
            else:
                urls = self._read_input_file_as_lines()

            url_string_iter = itertools.chain(url_string_iter, urls)

        base_url = self._args.base

        for url_string in url_string_iter:
            _logger.debug(__('Parsing URL {0}', url_string))

            if base_url:
                url_string = wpull.url.urljoin(base_url, url_string)

            url_info = self._factory.class_map['URLInfo'].parse(
                url_string, default_scheme=default_scheme)

            _logger.debug(__('Parsed URL {0}', url_info))

            if url_rewriter:
                url_info = url_rewriter.rewrite(url_info)
                _logger.debug(__('Rewritten URL {0}', url_info))

            yield url_info

    def _build_url_rewriter(self):
        '''Build URL rewriter if needed.'''
        if self._args.escaped_fragment or self._args.strip_session_id:
            return self._factory.new(
                'URLRewriter',
                hash_fragment=self._args.escaped_fragment,
                session_id=self._args.strip_session_id
            )

    def _read_input_file_as_lines(self):
        '''Read lines from input file and return them.'''
        input_file = codecs.getreader(
            self._args.local_encoding or 'utf-8')(self._args.input_file)

        urls = [line.strip() for line in input_file if line.strip()]

        if not urls:
            raise ValueError(_('No URLs found in input file.'))

        return urls

    def _read_input_file_as_html(self):
        '''Read input file as HTML and return the links.'''
        scrape_result = self._factory['HTMLScraper'].scrape_file(
            self._args.input_file,
            encoding=self._args.local_encoding or 'utf-8'
        )
        links = [context.link for context in scrape_result.link_contexts]

        return links

    def _build_url_filters(self):
        '''Create the URL filter instances.

        Returns:
            A list of URL filter instances
        '''
        args = self._args

        filters = [
            HTTPSOnlyFilter() if args.https_only else SchemeFilter(),
            RecursiveFilter(
                enabled=args.recursive, page_requisites=args.page_requisites
            ),
            SpanHostsFilter(
                self._url_infos,
                enabled=args.span_hosts,
                page_requisites='page-requisites' in args.span_hosts_allow,
                linked_pages='linked-pages' in args.span_hosts_allow,
            ),
            FollowFTPFilter(follow=args.follow_ftp),
        ]

        if args.no_parent:
            filters.append(ParentFilter())

        if args.domains or args.exclude_domains:
            filters.append(
                BackwardDomainFilter(args.domains, args.exclude_domains)
            )

        if args.hostnames or args.exclude_hostnames:
            filters.append(
                HostnameFilter(args.hostnames, args.exclude_hostnames)
            )

        if args.tries:
            filters.append(TriesFilter(args.tries))

        if args.level and args.recursive or args.page_requisites_level:
            filters.append(
                LevelFilter(args.level,
                            inline_max_depth=args.page_requisites_level)
            )

        if args.accept_regex or args.reject_regex:
            filters.append(RegexFilter(args.accept_regex, args.reject_regex))

        if args.include_directories or args.exclude_directories:
            filters.append(
                DirectoryFilter(
                    args.include_directories, args.exclude_directories
                )
            )

        if args.accept or args.reject:
            filters.append(BackwardFilenameFilter(args.accept, args.reject))

        return filters

    def _build_demux_document_scraper(self):
        '''Create demux document scraper.'''
        self._factory.new(
            'DemuxDocumentScraper', self._build_document_scrapers())

    def _build_document_scrapers(self):
        '''Create the document scrapers.

        Returns:
            A list of document scrapers
        '''
        html_parser = self._factory['HTMLParser']
        element_walker = self._factory.new('ElementWalker')

        scrapers = [
            self._factory.new(
                'HTMLScraper',
                html_parser,
                element_walker,
                followed_tags=self._args.follow_tags,
                ignored_tags=self._args.ignore_tags,
                only_relative=self._args.relative,
                robots=self._args.robots,
                encoding_override=self._args.remote_encoding,
            ),
        ]

        if 'css' in self._args.link_extractors:
            css_scraper = self._factory.new(
                'CSSScraper',
                encoding_override=self._args.remote_encoding,
            )
            scrapers.append(css_scraper)
            element_walker.css_scraper = css_scraper

        if 'javascript' in self._args.link_extractors:
            javascript_scraper = self._factory.new(
                'JavaScriptScraper',
                encoding_override=self._args.remote_encoding,
            )
            scrapers.append(javascript_scraper)
            element_walker.javascript_scraper = javascript_scraper

        if self._args.sitemaps:
            scrapers.append(self._factory.new(
                'SitemapScraper', html_parser,
                encoding_override=self._args.remote_encoding,
            ))

        return scrapers

    def _build_html_parser(self):
        '''Build HTML parser.'''
        if self._args.html_parser == 'html5lib':
            from wpull.document.htmlparse.html5lib_ import HTMLParser
        else:
            from wpull.document.htmlparse.lxml_ import HTMLParser

        self._factory.class_map['HTMLParser'] = HTMLParser
        self._factory.new('HTMLParser')

    def _build_url_table(self):
        '''Create the URL table.

        Returns:
            URLTable: An instance of :class:`.database.base.BaseURLTable`.
        '''
        if self._args.database_uri:
            self._factory.class_map[
                'URLTableImplementation'] = GenericSQLURLTable
            url_table_impl = self._factory.new(
                'URLTableImplementation', self._args.database_uri)
        else:
            url_table_impl = self._factory.new(
                'URLTableImplementation', path=self._args.database)

        url_table = self._factory.new('URLTable', url_table_impl)
        return url_table

    def _build_recorder(self):
        '''Create the Recorder.

        Returns:
            DemuxRecorder: An instance of :class:`.recorder.DemuxRecorder`.
        '''
        args = self._args
        recorders = []

        if args.warc_file:
            extra_fields = [
                ('robots', 'on' if args.robots else 'off'),
                ('wpull-arguments', str(args))
            ]

            for header_string in args.warc_header:
                name, value = header_string.split(':', 1)
                name = name.strip()
                value = value.strip()
                extra_fields.append((name, value))

            software_string = WARCRecorder.DEFAULT_SOFTWARE_STRING

            if args.phantomjs:
                software_string += ' PhantomJS/{0}'.format(
                    wpull.driver.phantomjs.get_version(exe_path=args.phantomjs_exe)
                )

            if args.youtube_dl:
                software_string += ' youtube-dl/{0}'.format(
                    wpull.coprocessor.youtubedl.get_version(exe_path=args.youtube_dl_exe)
                )

            url_table = self._factory['URLTable'] if args.warc_dedup else None

            recorders.append(
                self._factory.new(
                    'WARCRecorder',
                    args.warc_file,
                    params=WARCRecorderParams(
                        compress=not args.no_warc_compression,
                        extra_fields=extra_fields,
                        temp_dir=args.warc_tempdir,
                        log=args.warc_log,
                        appending=args.warc_append,
                        digests=args.warc_digests,
                        cdx=args.warc_cdx,
                        max_size=args.warc_max_size,
                        move_to=args.warc_move,
                        url_table=url_table,
                        software_string=software_string,
                    ),
                ))

        if args.server_response:
            recorders.append(self._factory.new('PrintServerResponseRecorder'))

        assert args.verbosity, \
            'Expect logging level. Got {}.'.format(args.verbosity)

        if args.verbosity in (LOG_VERBOSE, LOG_DEBUG) and args.progress != 'none':
            stream = self._new_encoded_stream(self._get_stderr())

            bar_style = args.progress == 'bar'

            if not stream.isatty():
                bar_style = False

            recorders.append(self._factory.new('ProgressRecorder',
                                               bar_style=bar_style,
                                               stream=stream))

        if args.warc_dedup:
            self._populate_visits()

        if args.output_document:
            recorders.append(self._factory.new(
                'OutputDocumentRecorder',
                args.output_document,
                with_headers=args.save_headers,
            ))

        return self._factory.new('DemuxRecorder', recorders)

    def _populate_visits(self):
        '''Populate the visits from the CDX into the URL table.'''
        iterable = wpull.warc.read_cdx(
            self._args.warc_dedup,
            encoding=self._args.local_encoding or 'utf-8'
        )

        missing_url_msg = _('The URL ("a") is missing from the CDX file.')
        missing_id_msg = _('The record ID ("u") is missing from the CDX file.')
        missing_checksum_msg = \
            _('The SHA1 checksum ("k") is missing from the CDX file.')

        nonlocal_var = {'counter': 0}

        def visits():
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
                nonlocal_var['counter'] += 1

        url_table = self.factory['URLTable']
        url_table.add_visits(visits())

        _logger.info(__(
            gettext.ngettext(
                'Loaded {num} record from CDX file.',
                'Loaded {num} records from CDX file.',
                nonlocal_var['counter']
            ),
            num=nonlocal_var['counter']
        ))

    def _build_processor(self):
        '''Create the Processor

        Returns:
            Processor: An instance of :class:`.processor.BaseProcessor`.
        '''
        web_processor = self._build_web_processor()
        ftp_processor = self._build_ftp_processor()
        return self._factory.new('Processor', web_processor, ftp_processor)

    def _build_web_processor(self):
        '''Build WebProcessor.'''
        args = self._args
        url_filter = self._factory.new('DemuxURLFilter',
                                       self._build_url_filters())
        document_scraper = self._factory['DemuxDocumentScraper']
        file_writer = self._build_file_writer()
        post_data = self._get_post_data()
        web_client = self._build_web_client()

        robots_txt_checker = self._build_robots_txt_checker()

        http_username = args.user or args.http_user
        http_password = args.password or args.http_password
        ftp_username = args.user or args.ftp_user
        ftp_password = args.password or args.ftp_password

        fetch_rule = self._factory.new(
            'FetchRule',
            url_filter=url_filter, robots_txt_checker=robots_txt_checker,
            http_login=(http_username, http_password),
            ftp_login=(ftp_username, ftp_password),
        )

        waiter = self._factory.new('Waiter',
                                   wait=args.wait,
                                   random_wait=args.random_wait,
                                   max_wait=args.waitretry)

        result_rule = self._factory.new(
            'ResultRule',
            ssl_verification=args.check_certificate,
            retry_connrefused=args.retry_connrefused,
            retry_dns_error=args.retry_dns_error,
            waiter=waiter,
            statistics=self._factory['Statistics'],
        )

        processing_rule = self._factory.new(
            'ProcessingRule',
            fetch_rule,
            document_scraper=document_scraper,
            sitemaps=self._args.sitemaps,
            url_rewriter=self._factory.get('URLRewriter'),
        )

        if args.phantomjs or args.youtube_dl or args.proxy_server:
            proxy_server, proxy_server_task, proxy_port = self._build_proxy_server()
            application = self._factory['Application']
            # XXX: Should we be sticking these into application?
            # We need to stick them somewhere so the Task doesn't get garbage
            # collected
            application.add_server_task(proxy_server_task)

        if args.phantomjs:
            phantomjs_coprocessor = self._build_phantomjs_coprocessor(proxy_port)
        else:
            phantomjs_coprocessor = None

        if args.youtube_dl:
            youtube_dl_coprocessor = self._build_youtube_dl_coprocessor(proxy_port)
        else:
            youtube_dl_coprocessor = None

        web_processor_instances = self._factory.new(
            'WebProcessorInstances',
            fetch_rule=fetch_rule,
            result_rule=result_rule,
            processing_rule=processing_rule,
            file_writer=file_writer,
            statistics=self._factory['Statistics'],
            phantomjs_coprocessor=phantomjs_coprocessor,
            youtube_dl_coprocessor=youtube_dl_coprocessor,
        )

        web_processor_fetch_params = self._factory.new(
            'WebProcessorFetchParams',
            post_data=post_data,
            strong_redirects=args.strong_redirects,
            content_on_error=args.content_on_error,
        )

        processor = self._factory.new('WebProcessor',
                                      web_client,
                                      args.directory_prefix,
                                      web_processor_fetch_params,
                                      web_processor_instances)

        return processor

    def _build_ftp_processor(self):
        '''Build FTPProcessor.'''
        ftp_client = self._build_ftp_client()

        fetch_params = self._factory.new(
            'FTPProcessorFetchParams',
            remove_listing=self._args.remove_listing
        )

        instances = self._factory.new(
            'FTPProcessorInstances',
            fetch_rule=self._factory['FetchRule'],
            result_rule=self._factory['ResultRule'],
            processing_rule=self._factory['ProcessingRule'],
            file_writer=self._factory['FileWriter'],
        )

        return self._factory.new(
            'FTPProcessor',
            ftp_client,
            self._args.directory_prefix,
            fetch_params,
            instances
        )

    def _build_ftp_client(self):
        '''Build FTP client.'''
        return self._factory.new(
            'FTPClient',
            connection_pool=self._factory['ConnectionPool'],
            recorder=self._factory['DemuxRecorder'],
            proxy_adapter=self._factory.instance_map.get('ProxyAdapter')
            )

    def _build_file_writer(self):
        '''Create the File Writer.

        Returns:
            FileWriter: An instance of :class:`.writer.BaseFileWriter`.
        '''
        args = self._args

        if args.delete_after or args.output_document:
            return self._factory.new('FileWriter')  # is a NullWriter

        use_dir = (len(args.urls) != 1 or args.page_requisites
                   or args.recursive)

        if args.use_directories == 'force':
            use_dir = True
        elif args.use_directories == 'no':
            use_dir = False

        os_type = 'windows' if 'windows' in args.restrict_file_names \
                  else 'unix'
        ascii_only = 'ascii' in args.restrict_file_names
        no_control = 'nocontrol' not in args.restrict_file_names

        if 'lower' in args.restrict_file_names:
            case = 'lower'
        elif 'upper' in args.restrict_file_names:
            case = 'upper'
        else:
            case = None

        path_namer = self._factory.new(
            'PathNamer',
            args.directory_prefix,
            index=args.default_page,
            use_dir=use_dir,
            cut=args.cut_dirs,
            protocol=args.protocol_directories,
            hostname=args.host_directories,
            os_type=os_type,
            ascii_only=ascii_only,
            no_control=no_control,
            case=case,
            max_filename_length=args.max_filename_length,
        )

        if args.recursive or args.page_requisites or args.continue_download:
            if args.clobber_method == 'disable':
                file_class = OverwriteFileWriter
            else:
                file_class = IgnoreFileWriter
        elif args.timestamping:
            file_class = TimestampingFileWriter
        else:
            file_class = AntiClobberFileWriter

        self._factory.class_map['FileWriter'] = file_class

        return self._factory.new(
            'FileWriter',
            path_namer,
            file_continuing=args.continue_download,
            headers_included=args.save_headers,
            local_timestamping=args.use_server_timestamps,
            adjust_extension=args.adjust_extension,
            content_disposition=args.content_disposition,
            trust_server_names=args.trust_server_names,
        )

    def _get_post_data(self):
        '''Return the post data.'''
        if self._args.post_data:
            return self._args.post_data
        elif self._args.post_file:
            return self._args.post_file.read()

    def _build_request_factory(self):
        '''Create the request factory.

        A request factory is any callable object that returns a
        :class:`.http.Request`. The callable must accept the same
        arguments to Request.

        Returns:
            A callable object
        '''
        def request_factory(*args, **kwargs):
            request = self._factory.class_map['Request'](*args, **kwargs)

            user_agent = self._args.user_agent or self.default_user_agent

            request.fields['User-Agent'] = user_agent

            if self._args.referer:
                request.fields['Referer'] = self._args.referer

            for header_string in self._args.header:
                request.fields.parse(header_string)

            if self._args.http_compression:
                request.fields['Accept-Encoding'] = 'gzip, deflate'

            return request

        return request_factory

    def _build_connection_pool(self):
        '''Create connection pool.'''
        args = self._args
        connect_timeout = args.connect_timeout
        read_timeout = args.read_timeout

        if args.timeout:
            connect_timeout = read_timeout = args.timeout

        if args.limit_rate:
            bandwidth_limiter = self.factory.new('BandwidthLimiter',
                                                 args.limit_rate)
        else:
            bandwidth_limiter = None

        connection_factory = functools.partial(
            Connection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=self._args.bind_address,
            bandwidth_limiter=bandwidth_limiter,
        )

        ssl_connection_factory = functools.partial(
            SSLConnection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=self._args.bind_address,
            ssl_context=self._build_ssl_options()
        )

        return self._factory.new(
            'ConnectionPool',
            resolver=self._build_resolver(),
            connection_factory=connection_factory,
            ssl_connection_factory=ssl_connection_factory
        )

    def _build_resolver(self):
        '''Build resolver.'''
        args = self._args
        dns_timeout = args.dns_timeout

        if args.timeout:
            dns_timeout = args.timeout

        if args.inet_family == 'IPv4':
            family = socket.AF_INET
        elif args.inet_family == 'IPv6':
            family = socket.AF_INET6
        elif args.prefer_family == 'IPv6':
            family = Resolver.PREFER_IPv6
        else:
            family = Resolver.PREFER_IPv4

        if self._factory.class_map['Resolver'] is NotImplemented:
            if args.always_getaddrinfo:
                self._factory.class_map['Resolver'] = Resolver
            else:
                self._factory.class_map['Resolver'] = PythonResolver

        return self._factory.new(
            'Resolver',
            family=family,
            timeout=dns_timeout,
            rotate=args.rotate_dns,
            cache_enabled=args.dns_cache,
        )

    def _build_http_client(self):
        '''Create the HTTP client.

        Returns:
            Client: An instance of :class:`.http.Client`.
        '''
        recorder = self._build_recorder()

        stream_factory = functools.partial(
            HTTPStream,
            ignore_length=self._args.ignore_length,
            keep_alive=self._args.http_keep_alive)

        proxy_adapter = self._build_proxy_adapter()

        return self._factory.new('HTTPClient',
                                 connection_pool=self._build_connection_pool(),
                                 recorder=recorder,
                                 stream_factory=stream_factory,
                                 proxy_adapter=proxy_adapter)

    def _build_proxy_adapter(self):
        '''Build HTTP proxy adapter.'''
        if self._args.no_proxy:
            return

        if self._args.https_proxy:
            http_proxy = self._args.http_proxy.split(':', 1)
            ssl_ = True
        elif self._args.http_proxy:
            http_proxy = self._args.http_proxy.split(':', 1)
            ssl_ = False
        else:
            return

        http_proxy[1] = int(http_proxy[1])

        use_connect = not self._args.no_secure_proxy_tunnel

        if self._args.proxy_user:
            authentication = (self._args.proxy_user, self._args.proxy_password)
        else:
            authentication = None

        return self._factory.new(
            'ProxyAdapter', http_proxy, ssl=ssl_, use_connect=use_connect,
            authentication=authentication)

    def _build_web_client(self):
        '''Build Web Client.'''
        cookie_jar = self._build_cookie_jar()
        http_client = self._build_http_client()

        redirect_factory = functools.partial(
            self._factory.class_map['RedirectTracker'],
            max_redirects=self._args.max_redirect
        )

        return self._factory.new(
            'WebClient',
            http_client,
            redirect_tracker_factory=redirect_factory,
            cookie_jar=cookie_jar,
            request_factory=self._build_request_factory(),
        )

    def _build_cookie_jar(self):
        '''Build the cookie jar'''

        if not self._args.cookies:
            return

        if self._args.load_cookies or self._args.save_cookies:
            self._factory.set('CookieJar', RelaxedMozillaCookieJar)

            cookie_jar = self._factory.new('CookieJar')

            if self._args.load_cookies:
                cookie_jar.load(self._args.load_cookies, ignore_discard=True)
        else:
            cookie_jar = self._factory.new('CookieJar')

        policy = self._factory.new('CookiePolicy', cookie_jar=cookie_jar)

        cookie_jar.set_policy(policy)

        _logger.debug(__('Loaded cookies: {0}', list(cookie_jar)))

        cookie_jar_wrapper = self._factory.new(
            'CookieJarWrapper',
            cookie_jar,
            save_filename=self._args.save_cookies,
            keep_session_cookies=True,
        )

        return cookie_jar_wrapper

    def _build_document_converter(self):
        '''Build the Document Converter.'''

        if not self._args.convert_links:
            return

        converter = self._factory.new(
            'BatchDocumentConverter',
            self._factory['HTMLParser'],
            self._factory['ElementWalker'],
            self._factory['URLTable'],
            backup=self._args.backup_converted
        )

        return converter

    def _build_phantomjs_coprocessor(self, proxy_port):
        '''Build proxy server and PhantomJS client. controller, coprocessor.'''
        page_settings = {}
        default_headers = NameValueRecord()

        for header_string in self._args.header:
            default_headers.parse(header_string)

        # Since we can only pass a one-to-one mapping to PhantomJS,
        # we put these last since NameValueRecord.items() will use only the
        # first value added for each key.
        default_headers.add('Accept-Language', '*')

        if not self._args.http_compression:
            default_headers.add('Accept-Encoding', 'identity')

        default_headers = dict(default_headers.items())

        if self._args.read_timeout:
            page_settings['resourceTimeout'] = self._args.read_timeout * 1000

        page_settings['userAgent'] = self._args.user_agent \
            or self.default_user_agent

        # Test early for executable
        wpull.driver.phantomjs.get_version(self._args.phantomjs_exe)

        phantomjs_params = PhantomJSParams(
            wait_time=self._args.phantomjs_wait,
            num_scrolls=self._args.phantomjs_scroll,
            smart_scroll=self._args.phantomjs_smart_scroll,
            snapshot=self._args.phantomjs_snapshot,
            custom_headers=default_headers,
            page_settings=page_settings,
            load_time=self._args.phantomjs_max_time,
        )

        extra_args = [
            '--proxy',
            '{}:{}'.format(self._args.proxy_server_address, proxy_port),
            '--ignore-ssl-errors=true'
        ]

        phantomjs_driver_factory = functools.partial(
            self._factory.class_map['PhantomJSDriver'],
            exe_path=self._args.phantomjs_exe,
            extra_args=extra_args,
        )

        phantomjs_coprocessor = self._factory.new(
            'PhantomJSCoprocessor',
            phantomjs_driver_factory,
            self._factory['ProcessingRule'],
            phantomjs_params,
            root_path=self._args.directory_prefix,
            warc_recorder=self.factory.get('WARCRecorder'),
        )

        return phantomjs_coprocessor

    def _build_youtube_dl_coprocessor(self, proxy_port):
        '''Build youtube-dl coprocessor.'''

        # Test early for executable
        wpull.coprocessor.youtubedl.get_version(self._args.youtube_dl_exe)

        coprocessor = self.factory.new(
            'YoutubeDlCoprocessor',
            self._args.youtube_dl_exe,
            (self._args.proxy_server_address, proxy_port),
            root_path=self._args.directory_prefix,
            user_agent = self._args.user_agent or self.default_user_agent
        )

        return coprocessor

    def _build_proxy_server(self):
        '''Build MITM proxy server.'''
        proxy_server = self._factory.new(
            'HTTPProxyServer',
            self.factory['HTTPClient'],
        )

        cookie_jar = self.factory.get('CookieJarWrapper')
        proxy_coprocessor = self.factory.new(
            'ProxyCoprocessor',
            proxy_server,
            self.factory['FetchRule'],
            self.factory['ResultRule'],
            cookie_jar=cookie_jar
        )

        proxy_socket = tornado.netutil.bind_sockets(
            self._args.proxy_server_port,
            address=self._args.proxy_server_address
        )[0]
        proxy_port = proxy_socket.getsockname()[1]

        proxy_server_task = trollius.async(
            trollius.start_server(proxy_server, sock=proxy_socket)
        )

        return proxy_server, proxy_server_task, proxy_port

    def _build_robots_txt_checker(self):
        '''Build robots.txt checker.'''
        if self._args.robots:
            robots_txt_pool = self._factory.new('RobotsTxtPool')
            robots_txt_checker = self._factory.new(
                'RobotsTxtChecker',
                web_client=self._factory['WebClient'],
                robots_txt_pool=robots_txt_pool
            )

            return robots_txt_checker

    def _build_ssl_options(self):
        '''Create the SSL options.

        The options must be accepted by the `ssl` module.

        Returns:
            SSLContext
        '''
        # Logic is based on tornado.netutil.ssl_options_to_context
        ssl_context = ssl.SSLContext(self._args.secure_protocol)

        if self._args.check_certificate:
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_context.load_verify_locations(self._load_ca_certs())
        else:
            ssl_context.verify_mode = ssl.CERT_NONE

        if self._args.strong_crypto:
            ssl_context.options |= ssl.OP_NO_SSLv2
            ssl_context.options |= ssl.OP_NO_SSLv3  # POODLE

            if hasattr(ssl, 'OP_NO_COMPRESSION'):
                ssl_context.options |= ssl.OP_NO_COMPRESSION  # CRIME
            else:
                _logger.warning(_('Unable to disable TLS compression.'))

        if self._args.certificate:
            ssl_context.load_cert_chain(
                self._args.certificate, self._args.private_key
            )

        if self._args.edg_file:
            ssl.RAND_egd(self._args.edg_file)

        if self._args.random_file:
            with open(self._args.random_file, 'rb') as in_file:
                # Use 16KB because Wget
                ssl.RAND_add(in_file.read(15360), 0.0)

        return ssl_context

    def _load_ca_certs(self):
        '''Load the Certificate Authority certificates.

        Returns:
            A filename to the bundled CA certs.
        '''
        if self._ca_certs_file:
            return self._ca_certs_file

        certs = set()

        if self._args.use_internal_ca_certs:
            pem_filename = os.path.join(
                os.path.dirname(__file__), 'cert', 'ca-bundle.pem'
            )
            certs.update(self._read_pem_file(pem_filename, from_package=True))

        if self._args.ca_directory:
            if os.path.isdir(self._args.ca_directory):
                for filename in os.listdir(self._args.ca_directory):
                    if os.path.isfile(filename):
                        certs.update(self._read_pem_file(filename))
            else:
                _logger.warning(__(
                    _('Certificate directory {path} does not exist.'),
                    path=self._args.ca_directory
                ))

        if self._args.ca_certificate:
            if os.path.isfile(self._args.ca_certificate):
                certs.update(self._read_pem_file(self._args.ca_certificate))
            else:
                _logger.warning(__(
                    _('Certificate file {path} does not exist.'),
                    path=self._args.ca_certificate
                ))

        self._ca_certs_file = certs_filename = tempfile.mkstemp()[1]

        def clean_certs_file():
            os.remove(certs_filename)

        atexit.register(clean_certs_file)

        with open(certs_filename, 'w+b') as certs_file:
            for cert in certs:
                certs_file.write(cert)

        _logger.debug('CA certs loaded.')

        return certs_filename

    def _read_pem_file(self, filename, from_package=False):
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

    def _warn_silly_options(self):
        '''Print warnings about any options that may be silly.'''
        if 'page-requisites' in self._args.span_hosts_allow \
           and not self._args.page_requisites:
            _logger.warning(
                _('Spanning hosts is allowed for page requisites, '
                  'but the page requisites option is not on.')
            )

        if 'linked-pages' in self._args.span_hosts_allow \
           and not self._args.recursive:
            _logger.warning(
                _('Spanning hosts is allowed for linked pages, '
                  'but the recursive option is not on.')
            )

        if self._args.warc_file and \
                (self._args.http_proxy or self._args.https_proxy):
            _logger.warning(_('WARC specifications do not handle proxies.'))

        if self._args.no_secure_proxy_tunnel:
            _logger.warning(_('HTTPS without encryption is enabled.'))

        if (self._args.password or self._args.ftp_password or
                self._args.http_password or self._args.proxy_password) and \
                self._args.warc_file:
            _logger.warning(
                _('Your password is recorded in the WARC file.'))

    def _warn_unsafe_options(self):
        '''Print warnings about any enabled hazardous options.

        This function will print messages complaining about:

        * ``--save-headers``
        * ``--no-iri``
        * ``--output-document``
        * ``--ignore-fatal-errors``
        '''
        enabled_options = []

        for option_name in self.UNSAFE_OPTIONS:
            if getattr(self._args, option_name):
                enabled_options.append(option_name)

        if enabled_options:
            _logger.warning(__(
                _('The following unsafe options are enabled: {list}.'),
                list=enabled_options
            ))
            _logger.warning(
                _('The use of unsafe options may lead to unexpected behavior '
                    'or file corruption.'))

    def _get_stderr(self):
        '''Return stderr or something else if under unit testing.'''
        if self._unit_test:
            return sys.stdout
        else:
            return sys.stderr
