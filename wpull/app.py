# encoding=utf-8
import atexit
import gettext
import itertools
import logging
import os.path
import ssl
import sys
import tempfile
import tornado.ioloop

from wpull.database import URLTable
from wpull.document import HTMLScraper, CSSScraper
from wpull.engine import Engine
from wpull.hook import HookEnvironment
from wpull.http import (Client, Connection, HostConnectionPool, ConnectionPool,
    Request)
from wpull.network import Resolver
from wpull.processor import WebProcessor
from wpull.recorder import (WARCRecorder, DemuxRecorder,
    PrintServerResponseRecorder, ProgressRecorder)
from wpull.url import (URLInfo, BackwardDomainFilter, TriesFilter, LevelFilter,
    RecursiveFilter, SpanHostsFilter, ParentFilter, RegexFilter, HTTPFilter,
    DirectoryFilter, HostnameFilter)
import wpull.version
from wpull.waiter import LinearWaiter
from wpull.writer import (PathNamer, NullWriter, OverwriteFileWriter,
    IgnoreFileWriter, TimestampingFileWriter, AntiClobberFileWriter)


# Module lua is imported later on demand.
_logger = logging.getLogger(__name__)
_ = gettext.gettext


class Builder(object):
    # TODO: expose the instances built so we can access stuff like Stats
    def __init__(self, args):
        self._args = args
        self._classes = {
            'URLInfo': URLInfo,
            'URLTable': URLTable,
            'HTMLScraper': HTMLScraper,
            'CSSScraper': Engine,
            'Client': Client,
            'Connection': Connection,
            'HostConnectionPool': HostConnectionPool,
            'ConnectionPool': ConnectionPool,
            'Request': Request,
            'Resolver': Resolver,
            'WebProcessor': WebProcessor,
            'WARCRecorder': WARCRecorder,
            'DemuxRecorder': DemuxRecorder,
            'PrintServerResponseRecorder': PrintServerResponseRecorder,
            'ProgressRecorder': ProgressRecorder,
            'Waiter': LinearWaiter,
            'PathNamer': PathNamer,
            'Engine': Engine,
        }
        self._url_infos = tuple(self._build_input_urls())
        self._ca_certs_file = None

    def build(self):
        self._setup_logging()
        self._setup_file_logger()
        self._install_script_hooks()

        url_table = self._build_url_table()
        processor = self._build_processor()
        http_client = self._build_http_client()

        return self._classes['Engine'](
            url_table,
            http_client,
            processor,
            concurrent=self._args.concurrent,
        )

    def build_and_run(self):
        io_loop = tornado.ioloop.IOLoop.current()
        engine = self.build()
        exit_code = io_loop.run_sync(engine)
        return exit_code

    def _setup_logging(self):
        logging.basicConfig(
            level=self._args.verbosity or logging.INFO,
            format='%(levelname)s %(message)s')

        if self._args.verbosity == logging.DEBUG:
            tornado.ioloop.IOLoop.current().set_blocking_log_threshold(5)

    def _setup_file_logger(self):
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

        handler = logging.FileHandler(filename, mode)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        if args.verbosity == logging.DEBUG:
            handler.setLevel(logging.DEBUG)
        else:
            handler.setLevel(logging.INFO)

    def _install_script_hooks(self):
        if self._args.python_script:
            self._install_python_script(self._args.python_script)
        elif self._args.lua_script:
            self._install_lua_script(self._args.lua_script)

    def _install_python_script(self, filename):
        _logger.info(_('Using Python hook script {filename}.').format(
            filename=filename))

        hook_environment = HookEnvironment()

        self._setup_hook_environment(hook_environment)

        with open(filename, 'rb') as in_file:
            code = compile(in_file.read(), filename, 'exec')
            context = {'wpull_hook': hook_environment}
            exec(code, context, context)

    def _install_lua_script(self, filename):
        _logger.info(_('Using Lua hook script {filename}.').format(
            filename=filename))

        lua = wpull.hook.load_lua()
        hook_environment = HookEnvironment(is_lua=True)

        self._setup_hook_environment(hook_environment)

        lua_globals = lua.globals()
        lua_globals.wpull_hook = hook_environment

        with open(filename, 'rb') as in_file:
            lua.execute(in_file.read())

    def _setup_hook_environment(self, hook_environment):
        self._classes['Engine'] = hook_environment.engine_factory
        self._classes['WebProcessor'] = \
            hook_environment.web_processor_factory
        self._classes['Resolver'] = hook_environment.resolver_factory

    def _build_input_urls(self, default_scheme='http'):
        if self._args.input_file:
            url_string_iter = itertools.chain(
                self._args.urls,
                self._args.input_file)
        else:
            url_string_iter = self._args.urls

        for url_string in url_string_iter:
            url_info = self._classes['URLInfo'].parse(
                url_string, default_scheme=default_scheme)
            _logger.debug('Parsed URL {0}'.format(url_info))
            yield url_info

    def _build_url_filters(self):
        args = self._args

        filters = [
            HTTPFilter(),
            BackwardDomainFilter(args.domains, args.exclude_domains),
            HostnameFilter(args.hostnames, args.exclude_hostnames),
            TriesFilter(args.tries),
            RecursiveFilter(args.recursive, args.page_requisites),
            LevelFilter(args.level),
            SpanHostsFilter(self._url_infos, enabled=args.span_hosts),
            RegexFilter(args.accept_regex, args.reject_regex),
            DirectoryFilter(args.include_directories,
                args.exclude_directories),
        ]

        if args.no_parent:
            filters.append(ParentFilter())

        return filters

    def _build_document_scrapers(self):
        scrapers = [
            HTMLScraper(
                followed_tags=self._args.follow_tags,
                ignored_tags=self._args.ignore_tags,
                only_relative=self._args.relative,
                robots=self._args.robots,
            ),
            CSSScraper(),
        ]

        return scrapers

    def _build_url_table(self):
        url_table = self._classes['URLTable'](path=self._args.database)
        url_table.add([url_info.url for url_info in self._url_infos])
        return url_table

    def _build_recorder(self):
        args = self._args
        recorders = []
        if args.warc_file:
            if args.no_warc_compression:
                warc_path = args.warc_file + '.warc'
            else:
                warc_path = args.warc_file + '.warc.gz'

            extra_fields = [
                ('robots', 'on' if args.robots else 'off'),
                ('wpull-arguments', str(args))
            ]

            for header_string in args.warc_header:
                name, value = header_string.split(':', 1)
                name = name.strip()
                value = value.strip()
                extra_fields.append((name, value))

            recorders.append(
                self._classes['WARCRecorder'](
                    warc_path,
                    compress=not args.no_warc_compression,
                    extra_fields=extra_fields,
                    temp_dir=args.warc_tempdir,
                    log=args.warc_log,
                    appending=args.warc_append,
                )
            )

        if args.server_response:
            recorders.append(self._classes['PrintServerResponseRecorder']())

        if args.verbosity in (logging.INFO, logging.DEBUG, logging.WARN, None):
            recorders.append(self._classes['ProgressRecorder']())

        return self._classes['DemuxRecorder'](recorders)

    def _build_processor(self):
        args = self._args
        url_filters = self._build_url_filters()
        document_scrapers = self._build_document_scrapers()

        file_writer = self._build_file_writer()

        waiter = self._classes['Waiter'](
            wait=args.wait,
            random_wait=args.random_wait,
            max_wait=args.waitretry
        )
        processor = self._classes['WebProcessor'](
            url_filters, document_scrapers, file_writer, waiter,
            request_factory=self._build_request_factory(),
            retry_connrefused=args.retry_connrefused,
            retry_dns_error=args.retry_dns_error,
            max_redirects=args.max_redirect,
            robots=args.robots,
        )

        return processor

    def _build_file_writer(self):
        args = self._args

        if args.delete_after:
            return NullWriter()

        use_dir = (len(args.urls) != 1 or args.page_requisites \
            or args.recursive)

        if args.use_directories == 'force':
            use_dir = True
        elif args.use_directories == 'no':
            use_dir = False

        path_namer = self._classes['PathNamer'](
            args.directory_prefix,
            index=args.default_page,
            use_dir=use_dir,
            cut=args.cut_dirs,
            protocol=args.protocol_directories,
            hostname=args.host_directories,
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

    def _build_request_factory(self):
        def request_factory(*args, **kwargs):
            request = self._classes['Request'].new(*args, **kwargs)

            if self._args.user_agent:
                user_agent = self._args.user_agent
            else:
                user_agent = 'Mozilla/5.0 (compatible) Wpull/{0}'.format(
                    wpull.version.__version__)

            request.fields['User-Agent'] = user_agent

            if self._args.referer:
                request.fields['Referer'] = self._args.referer

            for header_string in self._args.header:
                request.fields.parse(header_string)

            return request

        return request_factory

    def _build_http_client(self):
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

        resolver = self._classes['Resolver'](
            families=families,
            timeout=dns_timeout,
            rotate=args.rotate_dns
        )

        def connection_factory(*args, **kwargs):
            return self._classes['Connection'](
                *args,
                resolver=resolver,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                keep_alive=self._args.http_keep_alive,
                ssl_options=self._build_ssl_options(),
                **kwargs)

        def host_connection_pool_factory(*args, **kwargs):
            return self._classes['HostConnectionPool'](
                *args, connection_factory=connection_factory, **kwargs)

        connection_pool = self._classes['ConnectionPool'](
            host_connection_pool_factory=host_connection_pool_factory)
        recorder = self._build_recorder()

        return self._classes['Client'](
            connection_pool=connection_pool, recorder=recorder)

    def _build_ssl_options(self):
        ssl_options = {}

        if self._args.check_certificate:
            ssl_options['cert_reqs'] = ssl.CERT_REQUIRED
            ssl_options['ca_certs'] = self._load_ca_certs()
        else:
            ssl_options['cert_reqs'] = ssl.CERT_NONE

        return ssl_options

    def _load_ca_certs(self):
        if self._ca_certs_file:
            return self._ca_certs_file

        certs = set()

        if self._args.use_internal_ca_certs:
            pem_filename = os.path.join(os.path.dirname(__file__),
                'cert', 'ca-bundle.pem')
            certs.update(self._read_pem_file(pem_filename))

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

    def _read_pem_file(self, filename):
        _logger.debug('Reading PEM {0}.'.format(filename))

        with open(filename, 'rb') as in_file:
            return wpull.util.filter_pem(in_file.read())
