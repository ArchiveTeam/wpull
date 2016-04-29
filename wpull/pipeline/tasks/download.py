import asyncio
import datetime
import gettext
import json
import logging
import tempfile
import itertools
import functools
import sys

import tornado.netutil

from wpull.application.hook import HookableMixin
from wpull.application.options import LOG_VERBOSE, LOG_DEBUG
from wpull.backport.logging import BraceMessage as __
from wpull.cookie import BetterMozillaCookieJar
from wpull.processor.coprocessor.phantomjs import PhantomJSParams
from wpull.namevalue import NameValueRecord
from wpull.network.connection import Connection, SSLConnection
from wpull.network.dns import IPFamilyPreference
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.session import ItemSession
from wpull.proxy.client import HTTPProxyConnectionPool
from wpull.recorder.warc import WARCRecorder, WARCRecorderParams
from wpull.stats import Statistics
from wpull.pipeline.app import AppSession, new_encoded_stream
import wpull.resmon
import wpull.string
from wpull.urlfilter import HTTPSOnlyFilter, SchemeFilter, RecursiveFilter, \
    FollowFTPFilter, SpanHostsFilter, ParentFilter, BackwardDomainFilter, \
    HostnameFilter, TriesFilter, RegexFilter, DirectoryFilter, \
    BackwardFilenameFilter, LevelFilter
from wpull.protocol.http.stream import Stream as HTTPStream
import wpull.util
import wpull.processor.coprocessor.youtubedl
import wpull.driver.phantomjs
from wpull.writer import OverwriteFileWriter, IgnoreFileWriter, \
    TimestampingFileWriter, AntiClobberFileWriter
import wpull.application.hook

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class StatsStartTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        statistics = session.factory.new('Statistics')
        statistics.quota = session.args.quota
        statistics.start()


class StatsStopTask(ItemTask[AppSession], HookableMixin):
    def __init__(self):
        super().__init__()
        self.event_dispatcher.register('StatsStopTask.finishing_statistics')

    @asyncio.coroutine
    def process(self, session: AppSession):
        statistics = session.factory['Statistics']
        statistics.stop()

        # TODO: human_format_speed arg
        self._print_stats(statistics)

        self.event_dispatcher.notify('StatsStopTask.finishing_statistics', session, statistics)

    @classmethod
    def _print_stats(cls, stats: Statistics, human_format_speed: bool=True):
        '''Log the final statistics to the user.'''
        time_length = datetime.timedelta(
            seconds=int(stats.stop_time - stats.start_time)
        )
        file_size = wpull.string.format_size(stats.size)

        if stats.bandwidth_meter.num_samples:
            speed = stats.bandwidth_meter.speed()

            if human_format_speed:
                speed_size_str = wpull.string.format_size(speed)
            else:
                speed_size_str = '{:.1f} b'.format(speed * 8)
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

    @staticmethod
    @wpull.application.hook.event_function('StatsStopTask.finishing_statistics')
    def plugin_finishing_statistics(app_session: AppSession, statistics: Statistics):
        '''Callback containing final statistics.

        Args:
            start_time (float): timestamp when the engine started
            end_time (float): timestamp when the engine stopped
            num_urls (int): number of URLs downloaded
            bytes_downloaded (int): size of files downloaded in bytes
        '''


class ParserSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_html_parser(session)
        self._build_demux_document_scraper(session)

    @classmethod
    def _build_html_parser(cls, session: AppSession):
        if session.args.html_parser == 'html5lib':
            from wpull.document.htmlparse.html5lib_ import HTMLParser
        else:
            from wpull.document.htmlparse.lxml_ import HTMLParser

        session.factory.class_map['HTMLParser'] = HTMLParser
        session.factory.new('HTMLParser')

    @classmethod
    def _build_demux_document_scraper(cls, session: AppSession):
        '''Create demux document scraper.'''
        session.factory.new(
            'DemuxDocumentScraper', cls._build_document_scrapers(session))

    @classmethod
    def _build_document_scrapers(cls, session: AppSession):
        '''Create the document scrapers.

        Returns:
            A list of document scrapers
        '''
        html_parser = session.factory['HTMLParser']
        element_walker = session.factory.new('ElementWalker')

        scrapers = [
            session.factory.new(
                'HTMLScraper',
                html_parser,
                element_walker,
                followed_tags=session.args.follow_tags,
                ignored_tags=session.args.ignore_tags,
                only_relative=session.args.relative,
                robots=session.args.robots,
                encoding_override=session.args.remote_encoding,
            ),
        ]

        if 'css' in session.args.link_extractors:
            css_scraper = session.factory.new(
                'CSSScraper',
                encoding_override=session.args.remote_encoding,
            )
            scrapers.append(css_scraper)
            element_walker.css_scraper = css_scraper

        if 'javascript' in session.args.link_extractors:
            javascript_scraper = session.factory.new(
                'JavaScriptScraper',
                encoding_override=session.args.remote_encoding,
            )
            scrapers.append(javascript_scraper)
            element_walker.javascript_scraper = javascript_scraper

        if session.args.sitemaps:
            scrapers.append(session.factory.new(
                'SitemapScraper', html_parser,
                encoding_override=session.args.remote_encoding,
            ))

        return scrapers


class URLFiltersSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_url_rewriter(session)
        session.factory.new('DemuxURLFilter', self._build_url_filters(session))

    @classmethod
    def _build_url_rewriter(cls, session: AppSession):
        '''Build URL rewriter if needed.'''
        if session.args.escaped_fragment or session.args.strip_session_id:
            return session.factory.new(
                'URLRewriter',
                hash_fragment=session.args.escaped_fragment,
                session_id=session.args.strip_session_id
            )

    @classmethod
    def _build_url_filters(cls, session: AppSession):
        '''Create the URL filter instances.

        Returns:
            A list of URL filter instances
        '''
        args = session.args

        filters = [
            HTTPSOnlyFilter() if args.https_only else SchemeFilter(),
            RecursiveFilter(
                enabled=args.recursive, page_requisites=args.page_requisites
            ),
            FollowFTPFilter(follow=args.follow_ftp),
            SpanHostsFilter(
                tuple(session.factory['URLTable'].get_hostnames()),
                enabled=args.span_hosts,
                page_requisites='page-requisites' in args.span_hosts_allow,
                linked_pages='linked-pages' in args.span_hosts_allow,
            )
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


class NetworkSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_resolver(session)
        self._build_connection_pool(session)

    @classmethod
    def _build_resolver(cls, session: AppSession):
        '''Build resolver.'''
        args = session.args
        dns_timeout = args.dns_timeout

        if args.timeout:
            dns_timeout = args.timeout

        if args.inet_family == 'IPv4':
            family = IPFamilyPreference.ipv4_only
        elif args.inet_family == 'IPv6':
            family = IPFamilyPreference.ipv6_only
        elif args.prefer_family == 'IPv6':
            family = IPFamilyPreference.prefer_ipv6
        elif args.prefer_family == 'IPv4':
            family = IPFamilyPreference.prefer_ipv4
        else:
            family = IPFamilyPreference.any

        return session.factory.new(
            'Resolver',
            family=family,
            timeout=dns_timeout,
            rotate=args.rotate_dns,
            cache=session.factory.class_map['Resolver'].new_cache() if args.dns_cache else None,
        )

    @classmethod
    def _build_connection_pool(cls, session: AppSession):
        '''Create connection pool.'''
        args = session.args
        connect_timeout = args.connect_timeout
        read_timeout = args.read_timeout

        if args.timeout:
            connect_timeout = read_timeout = args.timeout

        if args.limit_rate:
            bandwidth_limiter = session.factory.new('BandwidthLimiter',
                                                    args.limit_rate)
        else:
            bandwidth_limiter = None

        connection_factory = functools.partial(
            Connection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=session.args.bind_address,
            bandwidth_limiter=bandwidth_limiter,
        )

        ssl_connection_factory = functools.partial(
            SSLConnection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=session.args.bind_address,
            ssl_context=session.ssl_context,
        )

        if not session.args.no_proxy:
            if session.args.https_proxy:
                http_proxy = session.args.http_proxy.split(':', 1)
                proxy_ssl = True
            elif session.args.http_proxy:
                http_proxy = session.args.http_proxy.split(':', 1)
                proxy_ssl = False
            else:
                http_proxy = None
                proxy_ssl = None

            if http_proxy:
                http_proxy[1] = int(http_proxy[1])

                if session.args.proxy_user:
                    authentication = (session.args.proxy_user,
                                      session.args.proxy_password)
                else:
                    authentication = None

                session.factory.class_map['ConnectionPool'] = \
                    HTTPProxyConnectionPool

                host_filter = session.factory.new(
                    'ProxyHostFilter',
                    accept_domains=session.args.proxy_domains,
                    reject_domains=session.args.proxy_exclude_domains,
                    accept_hostnames=session.args.proxy_hostnames,
                    reject_hostnames=session.args.proxy_exclude_hostnames
                )

                return session.factory.new(
                    'ConnectionPool',
                    http_proxy,
                    proxy_ssl=proxy_ssl,
                    authentication=authentication,
                    resolver=session.factory['Resolver'],
                    connection_factory=connection_factory,
                    ssl_connection_factory=ssl_connection_factory,
                    host_filter=host_filter,
                )

        return session.factory.new(
            'ConnectionPool',
            resolver=session.factory['Resolver'],
            connection_factory=connection_factory,
            ssl_connection_factory=ssl_connection_factory
        )


class ClientSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_web_client(session)
        self._build_ftp_client(session)

    @classmethod
    def _build_request_factory(cls, session: AppSession):
        '''Create the request factory.

        A request factory is any callable object that returns a
        :class:`.http.Request`. The callable must accept the same
        arguments to Request.

        Returns:
            A callable object
        '''
        def request_factory(*args, **kwargs):
            request = session.factory.class_map['Request'](*args, **kwargs)

            user_agent = session.args.user_agent or session.default_user_agent

            request.fields['User-Agent'] = user_agent

            if session.args.referer:
                request.fields['Referer'] = session.args.referer

            for header_string in session.args.header:
                request.fields.parse(header_string)

            if session.args.http_compression:
                request.fields['Accept-Encoding'] = 'gzip, deflate'

            if session.args.no_cache:
                request.fields['Cache-Control'] = 'no-cache, must-revalidate'
                request.fields['Pragma'] = 'no-cache'

            return request

        return request_factory

    @classmethod
    def _build_http_client(cls, session: AppSession):
        '''Create the HTTP client.

        Returns:
            Client: An instance of :class:`.http.Client`.
        '''
        # TODO:
        # recorder = self._build_recorder()

        stream_factory = functools.partial(
            HTTPStream,
            ignore_length=session.args.ignore_length,
            keep_alive=session.args.http_keep_alive)

        return session.factory.new(
            'HTTPClient',
            connection_pool=session.factory['ConnectionPool'],
            stream_factory=stream_factory
         )

    @classmethod
    def _build_web_client(cls, session: AppSession):
        '''Build Web Client.'''
        cookie_jar = cls._build_cookie_jar(session)
        http_client = cls._build_http_client(session)

        redirect_factory = functools.partial(
            session.factory.class_map['RedirectTracker'],
            max_redirects=session.args.max_redirect
        )

        return session.factory.new(
            'WebClient',
            http_client,
            redirect_tracker_factory=redirect_factory,
            cookie_jar=cookie_jar,
            request_factory=cls._build_request_factory(session),
        )

    @classmethod
    def _build_cookie_jar(cls, session: AppSession):
        '''Build the cookie jar'''

        if not session.args.cookies:
            return

        if session.args.load_cookies or session.args.save_cookies:
            session.factory.set('CookieJar', BetterMozillaCookieJar)

            cookie_jar = session.factory.new('CookieJar')

            if session.args.load_cookies:
                cookie_jar.load(session.args.load_cookies, ignore_discard=True)
        else:
            cookie_jar = session.factory.new('CookieJar')

        policy = session.factory.new('CookiePolicy', cookie_jar=cookie_jar)

        cookie_jar.set_policy(policy)

        _logger.debug(__('Loaded cookies: {0}', list(cookie_jar)))

        cookie_jar_wrapper = session.factory.new(
            'CookieJarWrapper',
            cookie_jar,
            save_filename=session.args.save_cookies,
            keep_session_cookies=session.args.keep_session_cookies,
        )

        return cookie_jar_wrapper

    @classmethod
    def _build_ftp_client(cls, session: AppSession):
        '''Build FTP client.'''
        return session.factory.new(
            'FTPClient',
            connection_pool=session.factory['ConnectionPool'],
            # TODO: recorder
            # recorder=session.factory['DemuxRecorder'],
        )


class FileWriterSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_file_writer(session)

    @classmethod
    def _build_file_writer(cls, session: AppSession):
        '''Create the File Writer.

        Returns:
            FileWriter: An instance of :class:`.writer.BaseFileWriter`.
        '''
        args = session.args

        if args.delete_after or args.output_document:
            return session.factory.new('FileWriter')  # is a NullWriter

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

        path_namer = session.factory.new(
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

        session.factory.class_map['FileWriter'] = file_class

        return session.factory.new(
            'FileWriter',
            path_namer,
            file_continuing=args.continue_download,
            headers_included=args.save_headers,
            local_timestamping=args.use_server_timestamps,
            adjust_extension=args.adjust_extension,
            content_disposition=args.content_disposition,
            trust_server_names=args.trust_server_names,
        )


class ProxyServerSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        pass


    @classmethod
    def _build_proxy_server(cls, session: AppSession):
        '''Build MITM proxy server.'''
        proxy_server = session.factory.new(
            'HTTPProxyServer',
            session.factory['HTTPClient'],
        )

        cookie_jar = session.factory.get('CookieJarWrapper')
        proxy_coprocessor = session.factory.new(
            'ProxyCoprocessor',
            proxy_server,
            session.factory['FetchRule'],
            session.factory['ResultRule'],
            cookie_jar=cookie_jar
        )

        proxy_socket = tornado.netutil.bind_sockets(
            session.args.proxy_server_port,
            address=session.args.proxy_server_address
        )[0]
        proxy_port = proxy_socket.getsockname()[1]

        proxy_server_task = asyncio.async(
            asyncio.start_server(proxy_server, sock=proxy_socket)
        )

        session.background_async_tasks.append(proxy_server_task)
        session.async_servers.append(proxy_server_task)
        session.proxy_server_port = proxy_port


class ProcessorSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_processor(session)

    @classmethod
    def _build_processor(cls, session: AppSession):
        '''Create the Processor

        Returns:
            Processor: An instance of :class:`.processor.BaseProcessor`.
        '''
        web_processor = cls._build_web_processor(session)
        ftp_processor = cls._build_ftp_processor(session)
        delegate_processor = session.factory.new('Processor')

        delegate_processor.register('http', web_processor)
        delegate_processor.register('https', web_processor)
        delegate_processor.register('ftp', ftp_processor)

    @classmethod
    def _build_web_processor(cls, session: AppSession):
        '''Build WebProcessor.'''
        args = session.args
        url_filter = session.factory['DemuxURLFilter']
        document_scraper = session.factory['DemuxDocumentScraper']
        file_writer = session.factory['FileWriter']
        post_data = cls._get_post_data(session.args)
        web_client = session.factory['WebClient']

        robots_txt_checker = cls._build_robots_txt_checker(session)

        http_username = args.user or args.http_user
        http_password = args.password or args.http_password
        ftp_username = args.user or args.ftp_user
        ftp_password = args.password or args.ftp_password

        fetch_rule = session.factory.new(
            'FetchRule',
            url_filter=url_filter, robots_txt_checker=robots_txt_checker,
            http_login=(http_username, http_password),
            ftp_login=(ftp_username, ftp_password),
            duration_timeout=args.session_timeout,
        )

        waiter = session.factory.new(
            'Waiter',
            wait=args.wait,
            random_wait=args.random_wait,
            max_wait=args.waitretry)

        result_rule = session.factory.new(
            'ResultRule',
            ssl_verification=args.check_certificate,
            retry_connrefused=args.retry_connrefused,
            retry_dns_error=args.retry_dns_error,
            waiter=waiter,
            statistics=session.factory['Statistics'],
        )

        processing_rule = session.factory.new(
            'ProcessingRule',
            fetch_rule,
            document_scraper=document_scraper,
            sitemaps=session.args.sitemaps,
            url_rewriter=session.factory.get('URLRewriter'),
        )

        if args.phantomjs or args.youtube_dl or args.proxy_server:
            proxy_port = session.proxy_server_port

        if args.phantomjs:
            phantomjs_coprocessor = self._build_phantomjs_coprocessor(session, proxy_port)
        else:
            phantomjs_coprocessor = None

        if args.youtube_dl:
            youtube_dl_coprocessor = self._build_youtube_dl_coprocessor(session, proxy_port)
        else:
            youtube_dl_coprocessor = None

        web_processor_fetch_params = session.factory.new(
            'WebProcessorFetchParams',
            post_data=post_data,
            strong_redirects=args.strong_redirects,
            content_on_error=args.content_on_error,
        )

        processor = session.factory.new(
            'WebProcessor',
            web_client,
            args.directory_prefix,
            web_processor_fetch_params,

        return processor

    @classmethod
    def _build_ftp_processor(cls, session: AppSession):
        '''Build FTPProcessor.'''
        ftp_client = session.factory['FTPClient']

        fetch_params = session.factory.new(
            'FTPProcessorFetchParams',
            remove_listing=session.args.remove_listing,
            retr_symlinks=session.args.retr_symlinks,
            preserve_permissions=session.args.preserve_permissions,
            glob=session.args.glob,
        )

        return session.factory.new(
            'FTPProcessor',
            ftp_client,
            session.args.directory_prefix,
            fetch_params,
        )

    @classmethod
    def _get_post_data(cls, args):
        '''Return the post data.'''
        if args.post_data:
            return args.post_data
        elif args.post_file:
            return args.post_file.read()

    @classmethod
    def _build_phantomjs_coprocessor(cls, session: AppSession, proxy_port: int):
        '''Build proxy server and PhantomJS client. controller, coprocessor.'''
        page_settings = {}
        default_headers = NameValueRecord()

        for header_string in session.args.header:
            default_headers.parse(header_string)

        # Since we can only pass a one-to-one mapping to PhantomJS,
        # we put these last since NameValueRecord.items() will use only the
        # first value added for each key.
        default_headers.add('Accept-Language', '*')

        if not session.args.http_compression:
            default_headers.add('Accept-Encoding', 'identity')

        default_headers = dict(default_headers.items())

        if session.args.read_timeout:
            page_settings['resourceTimeout'] = session.args.read_timeout * 1000

        page_settings['userAgent'] = session.args.user_agent \
                                     or session.default_user_agent

        # Test early for executable
        wpull.driver.phantomjs.get_version(session.args.phantomjs_exe)

        phantomjs_params = PhantomJSParams(
            wait_time=session.args.phantomjs_wait,
            num_scrolls=session.args.phantomjs_scroll,
            smart_scroll=session.args.phantomjs_smart_scroll,
            snapshot=session.args.phantomjs_snapshot,
            custom_headers=default_headers,
            page_settings=page_settings,
            load_time=session.args.phantomjs_max_time,
        )

        extra_args = [
            '--proxy',
            '{}:{}'.format(session.args.proxy_server_address, proxy_port),
            '--ignore-ssl-errors=true'
        ]

        phantomjs_driver_factory = functools.partial(
            session.factory.class_map['PhantomJSDriver'],
            exe_path=session.args.phantomjs_exe,
            extra_args=extra_args,
        )

        phantomjs_coprocessor = session.factory.new(
            'PhantomJSCoprocessor',
            phantomjs_driver_factory,
            session.factory['ProcessingRule'],
            phantomjs_params,
            root_path=session.args.directory_prefix,
            warc_recorder=session.factory.get('WARCRecorder'),
        )

        return phantomjs_coprocessor

    @classmethod
    def _build_youtube_dl_coprocessor(cls, session: AppSession, proxy_port: int):
        '''Build youtube-dl coprocessor.'''

        # Test early for executable
        wpull.coprocessor.youtubedl.get_version(session.args.youtube_dl_exe)

        coprocessor = session.factory.new(
            'YoutubeDlCoprocessor',
            session.args.youtube_dl_exe,
            (session.args.proxy_server_address, proxy_port),
            root_path=session.args.directory_prefix,
            user_agent=session.args.user_agent or session.default_user_agent,
            warc_recorder=session.factory.get('WARCRecorder'),
            inet_family=session.args.inet_family,
            check_certificate=session.args.check_certificate
        )

        return coprocessor

    @classmethod
    def _build_robots_txt_checker(cls, session: AppSession):
        '''Build robots.txt checker.'''
        if session.args.robots:
            robots_txt_pool = session.factory.new('RobotsTxtPool')
            robots_txt_checker = session.factory.new(
                'RobotsTxtChecker',
                web_client=session.factory['WebClient'],
                robots_txt_pool=robots_txt_pool
            )

            return robots_txt_checker

    @classmethod
    def _build_recorder(cls, session: AppSession):
        '''Create the Recorder.

        Returns:
            DemuxRecorder: An instance of :class:`.recorder.DemuxRecorder`.
        '''
        args = session.args
        recorders = []

        if args.server_response:
            recorders.append(session.factory.new('PrintServerResponseRecorder'))

        assert args.verbosity, \
            'Expect logging level. Got {}.'.format(args.verbosity)

        if args.verbosity in (LOG_VERBOSE, LOG_DEBUG) and args.progress != 'none':
            stream = new_encoded_stream(session.factory['Application'].get_stderr())

            bar_style = args.progress == 'bar'

            if not stream.isatty():
                bar_style = False

            recorders.append(session.factory.new(
                'ProgressRecorder',
                bar_style=bar_style,
                stream=stream,
                human_format=not args.report_speed,
            ))

        if args.output_document:
            recorders.append(session.factory.new(
                'OutputDocumentRecorder',
                args.output_document,
                with_headers=args.save_headers,
            ))

        return session.factory.new('DemuxRecorder', recorders)


class ResmonSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        if not wpull.resmon.psutil:
            return

        paths = [session.args.directory_prefix, tempfile.gettempdir()]

        if session.args.warc_file:
            paths.append(session.args.warc_tempdir)

        session.factory.new(
            'ResourceMonitor',
            resource_paths=paths,
            min_memory=session.args.monitor_memory,
            min_disk=session.args.monitor_disk,
        )


class ResmonSleepTask(ItemTask[ItemSession]):
    @asyncio.coroutine
    def process(self, session: ItemSession):
        resource_monitor = session.app_session.factory['ResourceMonitor']

        if not resource_monitor:
            return

        resmon_semaphore = session.app_session.resource_monitor_semaphore

        if resmon_semaphore.locked():
            use_log = False
        else:
            use_log = True
            yield from resmon_semaphore.acquire()

        yield from self._polling_sleep(resource_monitor, log=use_log)

        if use_log:
            resource_monitor.release()

    @classmethod
    @asyncio.coroutine
    def _polling_sleep(cls, resource_monitor, log=False):
        for counter in itertools.count():
            resource_info = resource_monitor.check()

            if not resource_info:
                if log and counter:
                    _logger.info(_('Situation cleared.'))

                break

            if log and counter % 15 == 0:
                if resource_info.path:
                    _logger.warning(__(
                        _('Low disk space on {path} ({size} free).'),
                        path=resource_info.path,
                        size=wpull.string.format_size(resource_info.free)
                    ))
                else:
                    _logger.warning(__(
                        _('Low memory ({size} free).'),
                        size=wpull.string.format_size(resource_info.free)
                    ))

                _logger.warning(_('Waiting for operator to clear situation.'))

            yield from asyncio.sleep(60)


class ProcessTask(ItemTask[ItemSession]):
    @asyncio.coroutine
    def process(self, session: ItemSession):
        yield from session.app_session.factory['Processor'].process(session)


# class ParseTask(ItemTask[WorkItemT]):
#     @asyncio.coroutine
#     def process(self, work_item: WorkItemT):
#         pass
#
#
# class ExtractTask(ItemTask[WorkItemT]):
#     @asyncio.coroutine
#     def process(self, work_item: WorkItemT):
#         pass
#
#
# class WaitTask(ItemTask[WorkItemT]):
#     @asyncio.coroutine
#     def process(self, work_item: WorkItemT):
#         pass


class BackgroundAsyncTask(ItemTask[ItemSession]):
    @asyncio.coroutine
    def process(self, session: ItemSession):
        for task in session.app_session.background_async_tasks:
            if task.done():
                yield from task
