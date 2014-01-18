# encoding=utf-8
import itertools
import logging
import tornado.ioloop

from wpull.database import URLTable
from wpull.document import HTMLScraper, CSSScraper
from wpull.engine import Engine
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


_logger = logging.getLogger(__name__)


class Builder(object):
    # TODO: expose the instances built so we can access stuff like Stats
    def __init__(self, args):
        self._args = args
        self._url_infos = tuple(self._build_input_urls())

    def build(self):
        self._setup_logging()
        self._setup_file_logger()

        url_table = self._build_url_table()
        processor = self._build_processor()
        http_client = self._build_http_client()

        return Engine(
            url_table,
            http_client,
            processor,
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

    def _build_input_urls(self, default_scheme='http'):
        if self._args.input_file:
            url_string_iter = itertools.chain(
                self._args.urls,
                self._args.input_file)
        else:
            url_string_iter = self._args.urls

        for url_string in url_string_iter:
            url_info = URLInfo.parse(url_string, default_scheme=default_scheme)
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
        url_table = URLTable(path=self._args.database)
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
                WARCRecorder(
                    warc_path,
                    compress=not args.no_warc_compression,
                    extra_fields=extra_fields,
                    temp_dir=args.warc_tempdir,
                    log=args.warc_log,
                )
            )

        if args.server_response:
            recorders.append(PrintServerResponseRecorder())

        if args.verbosity in (logging.INFO, logging.DEBUG, logging.WARN, None):
            recorders.append(ProgressRecorder())

        return DemuxRecorder(recorders)

    def _build_processor(self):
        args = self._args
        url_filters = self._build_url_filters()
        document_scrapers = self._build_document_scrapers()

        file_writer = self._build_file_writer()

        waiter = LinearWaiter(
            wait=args.wait,
            random_wait=args.random_wait,
            max_wait=args.waitretry
        )
        processor = WebProcessor(
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

        path_namer = PathNamer(
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
            request = Request.new(*args, **kwargs)

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

        resolver = Resolver(families=families, timeout=dns_timeout,
            rotate=args.rotate_dns)

        def connection_factory(*args, **kwargs):
            return Connection(
                *args,
                resolver=resolver,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                keep_alive=self._args.http_keep_alive,
                **kwargs)

        def host_connection_pool_factory(*args, **kwargs):
            return HostConnectionPool(
                *args, connection_factory=connection_factory, **kwargs)

        connection_pool = ConnectionPool(
            host_connection_pool_factory=host_connection_pool_factory)
        recorder = self._build_recorder()

        return Client(connection_pool=connection_pool, recorder=recorder)
