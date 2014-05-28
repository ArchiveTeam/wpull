# encoding=utf-8
'''Application support.'''
import atexit
import codecs
import functools
import gettext
from http.cookiejar import CookieJar
import itertools
import logging
import os.path
import ssl
import sys
import tempfile

import tornado.ioloop
import tornado.testing

from wpull.converter import BatchDocumentConverter
from wpull.cookie import CookieLimitsPolicy, RelaxedMozillaCookieJar
from wpull.database import URLTable
from wpull.debug import DebugConsoleHandler
from wpull.engine import Engine
from wpull.factory import Factory
from wpull.hook import HookEnvironment
from wpull.http.client import Client
from wpull.http.connection import (Connection, ConnectionPool, HostConnectionPool,
    ConnectionParams)
from wpull.http.request import Request
from wpull.http.web import RedirectTracker, RichClient
from wpull.namevalue import NameValueRecord
from wpull.network import Resolver
from wpull.phantomjs import PhantomJSClient
from wpull.processor import (WebProcessor, PhantomJSController,
    WebProcessorFetchParams, WebProcessorInstances)
from wpull.proxy import HTTPProxyServer
from wpull.recorder import (WARCRecorder, DemuxRecorder,
    PrintServerResponseRecorder, ProgressRecorder, OutputDocumentRecorder,
    WARCRecorderParams)
from wpull.robotstxt import RobotsTxtPool
from wpull.scraper import (HTMLScraper, CSSScraper, DemuxDocumentScraper,
    SitemapScraper, JavaScriptScraper)
from wpull.stats import Statistics
from wpull.url import URLInfo
from wpull.urlfilter import (DemuxURLFilter, HTTPSOnlyFilter, HTTPFilter,
    BackwardDomainFilter, HostnameFilter, TriesFilter, RecursiveFilter, LevelFilter,
    SpanHostsFilter, RegexFilter, DirectoryFilter, BackwardFilenameFilter,
    ParentFilter)
from wpull.util import ASCIIStreamWriter
import wpull.version
from wpull.waiter import LinearWaiter
from wpull.wrapper import CookieJarWrapper
from wpull.writer import (PathNamer, NullWriter, OverwriteFileWriter,
    IgnoreFileWriter, TimestampingFileWriter, AntiClobberFileWriter)


# Module lua is imported later on demand.
_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Builder(object):
    '''Application builder.

    Args:
        args: Options from :class:`argparse.ArgumentParser`
    '''
    UNSAFE_OPTIONS = frozenset(['save_headers', 'no_iri', 'output_document'])

    def __init__(self, args):
        self.default_user_agent = 'Wpull/{0} (gzip)'.format(
            wpull.version.__version__)
        self._args = args
        self._factory = Factory({
            'BatchDocumentConverter': BatchDocumentConverter,
            'Client': Client,
            'CookieJar': CookieJar,
            'CookieJarWrapper': CookieJarWrapper,
            'CookiePolicy': CookieLimitsPolicy,
            'Connection': Connection,
            'ConnectionPool': ConnectionPool,
            'CSSScraper': CSSScraper,
            'DemuxDocumentScraper': DemuxDocumentScraper,
            'DemuxRecorder': DemuxRecorder,
            'DemuxURLFilter': DemuxURLFilter,
            'Engine': Engine,
            'HostConnectionPool': HostConnectionPool,
            'HTTPProxyServer': HTTPProxyServer,
            'HTMLScraper': HTMLScraper,
            'JavaScriptScraper': JavaScriptScraper,
            'OutputDocumentRecorder': OutputDocumentRecorder,
            'PathNamer': PathNamer,
            'PhantomJSClient': PhantomJSClient,
            'PhantomJSController': PhantomJSController,
            'PrintServerResponseRecorder': PrintServerResponseRecorder,
            'ProgressRecorder': ProgressRecorder,
            'RedirectTracker': RedirectTracker,
            'Request': Request,
            'Resolver': Resolver,
            'RichClient': RichClient,
            'RobotsTxtPool': RobotsTxtPool,
            'SitemapScraper': SitemapScraper,
            'Statistics': Statistics,
            'URLInfo': URLInfo,
            'URLTable': URLTable,
            'Waiter': LinearWaiter,
            'WARCRecorder': WARCRecorder,
            'WebProcessor': WebProcessor,
            'WebProcessorFetchParams': WebProcessorFetchParams,
            'WebProcessorInstances': WebProcessorInstances,
        })
        self._url_infos = tuple(self._build_input_urls())
        self._ca_certs_file = None
        self._file_log_handler = None
        self._console_log_handler = None

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
            Engine: An instance of :class:`.engine.Engine`.
        '''
        self._setup_logging()
        self._setup_console_logger()
        self._setup_file_logger()
        self._setup_debug_console()
        self._install_script_hooks()
        self._warn_unsafe_options()
        self._warn_silly_options()

        statistics = self._factory.new('Statistics')
        statistics.quota = self._args.quota
        statistics.required_url_infos.update(self._url_infos)

        url_table = self._build_url_table()
        processor = self._build_processor()

        engine = self._factory.new('Engine',
            url_table,
            processor,
            statistics,
            concurrent=self._args.concurrent,
        )

        self._setup_file_logger_close(engine)
        self._setup_console_logger_close(engine)

        return engine

    def build_and_run(self):
        '''Build and run the application.

        Returns:
            int: The exit status.
        '''
        io_loop = tornado.ioloop.IOLoop.current()
        engine = self.build()
        exit_code = io_loop.run_sync(engine)
        return exit_code

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
        assert self._args.verbosity

        root_logger = logging.getLogger()
        current_level = root_logger.getEffectiveLevel()
        min_level = logging.ERROR

        if self._args.verbosity == logging.WARNING:
            min_level = logging.WARNING

        if self._args.verbosity == logging.INFO \
        or self._args.warc_file \
        or self._args.output_file or self._args.append_output:
            min_level = logging.INFO

        if self._args.verbosity == logging.DEBUG:
            min_level = logging.DEBUG

        if current_level > min_level:
            root_logger.setLevel(min_level)
            root_logger.debug(
                'Wpull needs the root logger level set to {0}.'\
                    .format(min_level)
            )

    def _setup_console_logger(self):
        '''Set up the console logger.

        A handler and with a formatter is added to the root logger.
        '''
        stream = self._new_encoded_stream(sys.stderr)

        logger = logging.getLogger()
        self._console_log_handler = handler = logging.StreamHandler(stream)

        formatter = logging.Formatter('%(levelname)s %(message)s')

        handler.setFormatter(formatter)
        handler.setLevel(self._args.verbosity or logging.INFO)
        logger.addHandler(handler)

    def _setup_console_logger_close(self, engine):
        '''Add routine to remove log handler when the engine stops.'''
        def remove_handler():
            logger = logging.getLogger()
            logger.removeHandler(self._console_log_handler)
            self._console_log_handler = None

        if self._console_log_handler:
            engine.stop_event.handle(remove_handler)

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

    def _setup_file_logger_close(self, engine):
        '''Add routine that removes the file log handler when the engine stops.
        '''
        def remove_handler():
            logger = logging.getLogger()
            logger.removeHandler(self._file_log_handler)
            self._file_log_handler = None

        if self._file_log_handler:
            engine.stop_event.handle(remove_handler)

    def _install_script_hooks(self):
        '''Set up the scripts if any.'''
        if self._args.python_script:
            self._install_python_script(self._args.python_script)
        elif self._args.lua_script:
            self._install_lua_script(self._args.lua_script)

    def _install_python_script(self, filename):
        '''Load the Python script into an environment.'''
        _logger.info(_('Using Python hook script {filename}.').format(
            filename=filename))

        hook_environment = HookEnvironment(self._factory)

        self._setup_hook_environment(hook_environment)

        with open(filename, 'rb') as in_file:
            code = compile(in_file.read(), filename, 'exec')
            context = {'wpull_hook': hook_environment}
            exec(code, context, context)

    def _install_lua_script(self, filename):
        '''Load the Lua script into an environment.'''
        _logger.info(_('Using Lua hook script {filename}.').format(
            filename=filename))

        lua = wpull.hook.load_lua()
        hook_environment = HookEnvironment(self._factory, is_lua=True)

        self._setup_hook_environment(hook_environment)

        lua_globals = lua.globals()
        lua_globals.wpull_hook = hook_environment

        with open(filename, 'rb') as in_file:
            lua.execute(in_file.read())

    def _setup_hook_environment(self, hook_environment):
        '''Override the classes needed for script hooks.

        Args:
            hook_environment: A :class:`.hook.HookEnvironment` instance
        '''
        self._factory.set('Engine', hook_environment.engine_factory)
        self._factory.set('WebProcessor',
            hook_environment.web_processor_factory)
        self._factory.set('Resolver', hook_environment.resolver_factory)

    def _setup_debug_console(self):
        if not self._args.debug_console_port:
            return

        _logger.warning(
            _('Opened a debug console at localhost:{port}.')\
            .format(port=self._args.debug_console_port)
        )

        application = tornado.web.Application(
            [(r'/', DebugConsoleHandler)],
            builder=self
        )
        http_server = tornado.httpserver.HTTPServer(application)
        http_server.listen(self._args.debug_console_port, address='localhost')

    def _build_input_urls(self, default_scheme='http'):
        '''Read the URLs provided by the user.'''

        url_string_iter = self._args.urls or ()

        if self._args.input_file:
            if self._args.force_html:
                urls = self._read_input_file_as_html()
            else:
                urls = self._read_input_file_as_lines()

            url_string_iter = itertools.chain(url_string_iter, urls)

        sitemap_url_infos = set()
        base_url = self._args.base

        for url_string in url_string_iter:
            _logger.debug('Parsing URL {0}'.format(url_string))

            if base_url:
                url_string = wpull.url.urljoin(base_url, url_string)

            url_info = self._factory.class_map['URLInfo'].parse(
                url_string, default_scheme=default_scheme)

            _logger.debug('Parsed URL {0}'.format(url_info))
            yield url_info

            if self._args.sitemaps:
                sitemap_url_infos.update((
                     URLInfo.parse(
                         '{0}://{1}/robots.txt'.format(url_info.scheme,
                             url_info.hostname_with_port)
                     ),
                     URLInfo.parse(
                         '{0}://{1}/sitemap.xml'.format(url_info.scheme,
                             url_info.hostname_with_port)
                     )
                ))

        for url_info in sitemap_url_infos:
            yield url_info

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
        scrape_info = HTMLScraper.scrape_file(
            self._args.input_file,
            encoding=self._args.local_encoding or 'utf-8'
        )
        links = itertools.chain(
            scrape_info['inline_urls'], scrape_info['linked_urls']
        )

        return links

    def _build_url_filters(self):
        '''Create the URL filter instances.

        Returns:
            A list of URL filter instances
        '''
        args = self._args

        filters = [
            HTTPSOnlyFilter() if args.https_only else HTTPFilter(),
            RecursiveFilter(
                enabled=args.recursive, page_requisites=args.page_requisites
            ),
            SpanHostsFilter(
                self._url_infos,
                enabled=args.span_hosts,
                page_requisites='page-requisites' in args.span_hosts_allow,
                linked_pages='linked-pages' in args.span_hosts_allow,
            ),
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

        if args.level and args.recursive:
            filters.append(LevelFilter(args.level))

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

    def _build_document_scrapers(self):
        '''Create the document scrapers.

        Returns:
            A list of document scrapers
        '''
        scrapers = [
            self._factory.new(
                'HTMLScraper',
                followed_tags=self._args.follow_tags,
                ignored_tags=self._args.ignore_tags,
                only_relative=self._args.relative,
                robots=self._args.robots,
                encoding_override=self._args.remote_encoding,
            ),
            self._factory.new(
                'CSSScraper',
                encoding_override=self._args.remote_encoding,
            ),
            self._factory.new(
                'JavaScriptScraper',
                encoding_override=self._args.remote_encoding,
            ),
        ]

        if self._args.sitemaps:
            scrapers.append(self._factory.new(
                'SitemapScraper', encoding_override=self._args.remote_encoding,
            ))

        return scrapers

    def _build_url_table(self):
        '''Create the URL table.

        Returns:
            URLTable: An instance of :class:`.database.BaseURLTable`.
        '''
        url_table = self._factory.new('URLTable', path=self._args.database)
        url_table.add([url_info.url for url_info in self._url_infos])
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
                    wpull.phantomjs.get_version()
                )

            recorders.append(
                self._factory.new('WARCRecorder',
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
                        url_table=self._factory['URLTable'] if args.warc_dedup
                            else None,
                        software_string=software_string,
                    ),
                )
            )

        if args.server_response:
            recorders.append(self._factory.new('PrintServerResponseRecorder'))

        assert args.verbosity

        if args.verbosity in (logging.INFO, logging.DEBUG, logging.WARNING):
            stream = self._new_encoded_stream(sys.stderr)

            bar_style = args.progress == 'bar'

            if not stream.isatty():
                bar_style = False

            recorders.append(self._factory.new('ProgressRecorder',
                bar_style=bar_style, stream=stream))

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

        _logger.info(
            gettext.ngettext(
                'Loaded {num} record from CDX file.',
                'Loaded {num} records from CDX file.',
                nonlocal_var['counter']
            ).format(num=nonlocal_var['counter'])
        )

    def _build_processor(self):
        '''Create the Processor

        Returns:
            Processor: An instance of :class:`.processor.BaseProcessor`.
        '''
        args = self._args
        url_filter = self._factory.new('DemuxURLFilter',
            self._build_url_filters())
        document_scraper = self._factory.new('DemuxDocumentScraper',
            self._build_document_scrapers())
        file_writer = self._build_file_writer()
        post_data = self._get_post_data()
        converter = self._build_document_converter()
        rich_http_client = self._build_rich_http_client()
        phantomjs_controller = self._build_phantomjs_controller()

        waiter = self._factory.new('Waiter',
            wait=args.wait,
            random_wait=args.random_wait,
            max_wait=args.waitretry
        )

        web_processor_instances = self._factory.new(
            'WebProcessorInstances',
            url_filter=url_filter,
            document_scraper=document_scraper,
            file_writer=file_writer,
            waiter=waiter,
            statistics=self._factory['Statistics'],
            converter=converter,
            phantomjs_controller=phantomjs_controller,
        )

        web_processor_fetch_params = self._factory.new(
            'WebProcessorFetchParams',
            retry_connrefused=args.retry_connrefused,
            retry_dns_error=args.retry_dns_error,
            post_data=post_data,
            strong_redirects=args.strong_redirects,
            content_on_error=args.content_on_error,
        )

        processor = self._factory.new('WebProcessor',
            rich_http_client,
            args.directory_prefix,
            web_processor_fetch_params,
            web_processor_instances
        )

        return processor

    def _build_file_writer(self):
        '''Create the File Writer.

        Returns:
            FileWriter: An instance of :class:`.writer.BaseFileWriter`.
        '''
        args = self._args

        if args.delete_after or args.output_document:
            return NullWriter()

        use_dir = (len(args.urls) != 1 or args.page_requisites \
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

        path_namer = self._factory.new('PathNamer',
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

        return file_class(
            path_namer,
            file_continuing=args.continue_download,
            headers_included=args.save_headers,
            local_timestamping=args.use_server_timestamps
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
            request = self._factory.class_map['Request'].new(*args, **kwargs)

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

    def _build_http_client(self):
        '''Create the HTTP client.

        Returns:
            Client: An instance of :class:`.http.Client`.
        '''
        args = self._args
        dns_timeout = args.dns_timeout
        connect_timeout = args.connect_timeout
        read_timeout = args.read_timeout

        if args.timeout:
            dns_timeout = connect_timeout = read_timeout = args.timeout

        if args.inet_family == 'IPv4':
            families = [Resolver.IPv4]
        elif args.inet_family == 'IPv6':
            families = [Resolver.IPv6]
        elif args.prefer_family == 'IPv6':
            families = [Resolver.IPv6, Resolver.IPv4]
        else:
            families = [Resolver.IPv4, Resolver.IPv6]

        resolver = self._factory.new('Resolver',
            families=families,
            timeout=dns_timeout,
            rotate=args.rotate_dns,
            cache_enabled=args.dns_cache,
        )

        if self._args.bind_address:
            bind_address = (self._args.bind_address, 0)
        else:
            bind_address = None

        def connection_factory(*args, **kwargs):
            return self._factory.new('Connection',
                *args,
                resolver=resolver,
                params=ConnectionParams(
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                    keep_alive=(
                        self._args.http_keep_alive
                        and not self._args.ignore_length
                    ),
                    ssl_options=self._build_ssl_options(),
                    ignore_length=self._args.ignore_length,
                    bind_address=bind_address,
                ),
                **kwargs)

        def host_connection_pool_factory(*args, **kwargs):
            return self._factory.new('HostConnectionPool',
                *args, connection_factory=connection_factory, **kwargs)

        connection_pool = self._factory.new('ConnectionPool',
            host_connection_pool_factory=host_connection_pool_factory)
        recorder = self._build_recorder()

        return self._factory.new('Client',
            connection_pool=connection_pool, recorder=recorder)

    def _build_rich_http_client(self):
        '''Build Rich Client.'''
        cookie_jar = self._build_cookie_jar()
        http_client = self._build_http_client()

        if self._args.robots:
            robots_txt_pool = self._factory.new('RobotsTxtPool')
        else:
            robots_txt_pool = None

        redirect_factory = functools.partial(
            self._factory.class_map['RedirectTracker'],
            max_redirects=self._args.max_redirect
        )

        return self._factory.new(
            'RichClient',
            http_client,
            robots_txt_pool=robots_txt_pool,
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

        _logger.debug('Loaded cookies: {0}'.format(list(cookie_jar)))

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
            self._factory['URLTable'],
            backup=self._args.backup_converted
        )

        return converter

    def _build_phantomjs_controller(self):
        '''Build proxy server and PhantomJS client and controller.'''
        if not self._args.phantomjs:
            return

        proxy_server = self._factory.new(
            'HTTPProxyServer',
            self.factory['Client']
        )
        proxy_socket, proxy_port = tornado.testing.bind_unused_port()

        proxy_server.add_socket(proxy_socket)

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

        phantomjs_client = self._factory.new(
            'PhantomJSClient',
            'localhost:{0}'.format(proxy_port),
            page_settings=page_settings,
            default_headers=default_headers,
        )
        phantomjs_client.test_client_exe()

        phantomjs_controller = self._factory.new(
            'PhantomJSController',
            phantomjs_client,
            wait_time=self._args.phantomjs_wait,
            num_scrolls=self._args.phantomjs_scroll,
            warc_recorder=self.factory.get('WARCRecorder'),
            smart_scroll=self._args.phantomjs_smart_scroll,
            snapshot=self._args.phantomjs_snapshot,
        )

        return phantomjs_controller

    def _build_ssl_options(self):
        '''Create the SSL options.

        The options must be accepted by the `ssl` module.

        Returns:
            dict
        '''
        ssl_options = {}

        if self._args.check_certificate:
            ssl_options['cert_reqs'] = ssl.CERT_REQUIRED
            ssl_options['ca_certs'] = self._load_ca_certs()
        else:
            ssl_options['cert_reqs'] = ssl.CERT_NONE

        ssl_options['ssl_version'] = self._args.secure_protocol

        if self._args.certificate:
            ssl_options['certfile'] = self._args.certificate
            ssl_options['keyfile'] = self._args.private_key

        if self._args.edg_file:
            ssl.RAND_egd(self._args.edg_file)

        if self._args.random_file:
            with open(self._args.random_file, 'rb') as in_file:
                # Use 16KB because Wget
                ssl.RAND_add(in_file.read(15360), 0.0)

        return ssl_options

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
            for filename in os.listdir(self._args.ca_directory):
                if os.path.isfile(filename):
                    certs.update(self._read_pem_file(filename))

        if self._args.ca_certificate:
            certs.update(self._read_pem_file(self._args.ca_certificate))

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

    def _warn_unsafe_options(self):
        '''Print warnings about any enabled hazardous options.

        This function will print messages complaining about:

        * ``--save-headers``
        * ``--no-iri``
        * ``--output-document``
        '''
        enabled_options = []

        for option_name in self.UNSAFE_OPTIONS:
            if getattr(self._args, option_name):
                enabled_options.append(option_name)

        if enabled_options:
            _logger.warning(
                _('The following unsafe options are enabled: {list}.')\
                .format(list=enabled_options)
            )
            _logger.warning(
                _('The use of unsafe options may lead to unexpected behavior '
                    'or file corruption.'))
