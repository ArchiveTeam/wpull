# encoding=utf-8
'''Program options.'''
import gettext
import logging
import os
import ssl
import sys

import wpull.string
import wpull.version


if sys.version_info >= (2, 7):
    import argparse
else:
    from wpull.backport import argparse


_ = gettext.gettext
_logger = logging.getLogger(__name__)


class CommaChoiceListArgs(frozenset):
    '''Specialized frozenset.

    This class overrides the ``__contains__`` function to allow the use of
    the ``in`` operator for ArgumentParser's ``choices`` checking for
    comma separated lists. The function behaves differently only when
    the objects compared are `CommaChoiceListArgs`.
    '''
    def __contains__(self, item):
        if isinstance(item, CommaChoiceListArgs):
            return item <= self
        else:
            return frozenset.__contains__(self, item)


class AppHelpFormatter(argparse.HelpFormatter):
    def _metavar_formatter(self, action, default_metavar):
        # Modified from argparse
        if action.choices is not None:
            if action.metavar is not None:
                result = action.metavar + '='
            else:
                result = ''

            choice_strs = sorted([str(choice) for choice in action.choices])

            if isinstance(action.choices, CommaChoiceListArgs):
                result += '<%s>' % ','.join(choice_strs)
            else:
                result += '{%s}' % ','.join(choice_strs)

        elif action.metavar is not None:
            result = action.metavar
        else:
            result = default_metavar

        def format(tuple_size):
            if isinstance(result, tuple):
                return result
            else:
                return (result,) * tuple_size

        return format

    def _get_help_string(self, action):
        # Modified from argparse
        help = action.help

        if '%(default)' not in action.help:
            if action.default and not isinstance(action.default, bool) \
            and action.default is not argparse.SUPPRESS:
                defaulting_nargs = [argparse.OPTIONAL, argparse.ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    help += _(' (default: %(default)s)')
        return help


class AppArgumentParser(argparse.ArgumentParser):
    '''An Argument Parser that builds up the application options.'''
    # TODO: implement all sane options
    def __init__(self, *args, real_exit=True, **kwargs):
        super().__init__(
            *args,
            description=_('Wget-compatible web downloader.'),
            formatter_class=AppHelpFormatter,
            **kwargs
        )
        self._real_exit = real_exit
        self._ssl_version_map = None
        self._add_app_args()

    @classmethod
    def int_0_inf(cls, string):
        '''Convert string to int.

        If ``inf`` is supplied, it returns ``0``.
        '''
        if string == 'inf':
            return 0

        try:
            value = int(string)
        except ValueError as error:
            raise argparse.ArgumentTypeError(error)

        if value < 0:
            raise argparse.ArgumentTypeError(_('Value must not be negative.'))
        else:
            return value

    @classmethod
    def int_bytes(cls, string):
        '''Convert string describing size to int.'''
        if string[-1] in ('k', 'm'):
            value = cls.int_0_inf(string[:-1])
            unit = string[-1]
            if unit == 'k':
                value *= 2 ** 10
            else:
                value *= 2 ** 20
            return value
        else:
            return cls.int_0_inf(string)

    @classmethod
    def comma_list(cls, string):
        '''Convert a comma separated string to list.'''
        items = string.split(',')
        items = list([item.strip() for item in items])
        return items

    @classmethod
    def comma_choice_list(cls, string):
        '''Convert a comma separated string to `CommaChoiceListArgs`.'''
        items = string.split(',')
        items = CommaChoiceListArgs([item.strip() for item in items])
        return items

    def parse_args(self, args=None, namespace=None):
        if args is None:
            args = sys.argv[1:]

        encoding = self.get_argv_encoding(args)

        _logger.debug('Encoding: {0}'.format(encoding))

        args = super().parse_args(
            args=wpull.string.to_str(args, encoding=encoding),
            namespace=namespace
        )

        self._post_parse_args(args)
        return args

    @classmethod
    def get_argv_encoding(cls, argv):
        encoding = 'utf-8'
        stripped_argv = [
            wpull.string.printable_bytes(arg) for arg in
            wpull.string.to_bytes(argv, encoding='ascii', error='replace')
        ]

        try:
            index = stripped_argv.index(b'--local-encoding')
        except ValueError:
            pass
        else:
            encoding = stripped_argv[index + 1]

        return wpull.string.to_str(encoding)

    def exit(self, status=0, message=None):
        if self._real_exit:
            argparse.ArgumentParser.exit(self, status=status, message=message)
        else:
            raise ValueError(str(status) + ' ' + str(message))

    def _add_app_args(self):
        self.add_argument(
            'urls',
            nargs='*',
            metavar='URL',
            help=_('the URL to be downloaded'),
        )
        self._add_startup_args()
        self._add_log_and_input_args()
        self._add_download_args()
        self._add_directories_args()
        self._add_http_args()
        self._add_ssl_args()
        self._add_ftp_args()
        self._add_warc_args()
        self._add_recursive_args()
        self._add_accept_args()
        self._add_phantomjs_args()

    def _add_startup_args(self):
        group = self.add_argument_group(_('startup'))
        group.add_argument(
            '-V',
            '--version',
            action='version',
            version=wpull.version.__version__
        )
#         self.add_argument(
#             '-b',
#             '--background',
#             action='store_true',
#             help=_('run as background process')
#         )
#         self.add_argument(
#             '-e',
#             '--execute',
#             metavar='COMMAND',
#             action='append',
#             help=_('runs Wgetrc COMMAND'),
#         )
        script_group = group.add_mutually_exclusive_group()
        script_group.add_argument(
            '--python-script',
            metavar='FILE',
            help=_('load Python hook script from FILE')
        )
        script_group.add_argument(
            '--lua-script',
            metavar='FILE',
            help=_('load Lua hook script from FILE')
        )
        group.add_argument(
            '--database',
            metavar='FILE',
            default=':memory:',
            help=_('save database tables into FILE instead of memory'),
        )
        group.add_argument(
            '--concurrent',
            metavar='N',
            default=1,
            type=self.int_0_inf,
            help=_('run at most N downloads at the same time'),
        )

    def _add_log_and_input_args(self):
        group = self.add_argument_group(_('logging and input'))
        output_log_group = group.add_mutually_exclusive_group()
        output_log_group.add_argument(
            '-o',
            '--output-file',
            metavar='FILE',
            help=_('write program messages to FILE')
        )
        output_log_group.add_argument(
            '-a',
            '--append-output',
            metavar='FILE',
            help=_('append program messages to FILE')
        )
        verbosity_group = group.add_mutually_exclusive_group()
        verbosity_group.add_argument(
            '-d',
            '--debug',
            dest='verbosity',
            action='store_const',
            const=logging.DEBUG,
            help=_('print debugging messages')
        )
        verbosity_group.add_argument(
            '-q',
            '--quiet',
            dest='verbosity',
            action='store_const',
            const=logging.ERROR,
            help=_('do not print program messages')
        )
        verbosity_group.add_argument(
            '-v',
            '--verbose',
            dest='verbosity',
            action='store_const',
            const=logging.INFO,
            help=_('print informative program messages')
        )
        verbosity_group.add_argument(
            '-nv',
            '--no-verbose',
            dest='verbosity',
            action='store_const',
            const=logging.WARNING,
            help=_('print program warning and informative messages only')
        )
        group.add_argument(
            '--ascii-print',
            action='store_true',
            help=_('print program messages in ASCII only'),
        )
#         self.add_argument(
#             '--report-speed',
#             metavar='TYPE',
#             choices=['bits'],
#         )
        group.add_argument(
            '-i',
            '--input-file',
            metavar='FILE',
            type=argparse.FileType('rb'),
            help=_('download URLs listed in FILE'),
        )
        group.add_argument(
            '-F',
            '--force-html',
            action='store_true',
            help=_('read URL input files as HTML files')
        )
        group.add_argument(
            '-B',
            '--base',
            metavar='URL',
            help=_('resolves input relative URLs to URL')
        )
#         self.add_argument(
#             '--config',
#             metavar='FILE',
#             type=argparse.FileType('rt'),
#             help=_('read configuration from FILE'),
#         )

    def _add_download_args(self):
        group = self.add_argument_group('download')
        group.add_argument(
            '-t',
            '--tries',
            metavar='NUMBER',
            type=self.int_0_inf,
            help=_('try NUMBER of times on transient errors'),
            default=20,
        )
        group.add_argument(
            '--retry-connrefused',
            action='store_true',
            help=_('retry even if the server does not accept connections'),
        )
        group.add_argument(
            '--retry-dns-error',
            action='store_true',
            help=_('retry even if DNS fails to resolve hostname'),
        )
        group.add_argument(
            '-O',
            '--output-document',
            metavar='FILE',
            type=argparse.FileType('wb'),
            help=_('stream every document into FILE'),
        )
#         self.add_argument(
#             '--truncate-document',
#             action='store_true',
#             help=_('clear the output document after downloading'),
#         )
        clobber_group = group.add_mutually_exclusive_group()
        clobber_group.add_argument(
            '-nc',
            '--no-clobber',
            action='store_const',
            dest='clobber_method',
            const='disable',
            help=_('don’t use anti-clobbering filenames'),
        )
        group.add_argument(
            '-c',
            '--continue',
            action='store_true',
            dest='continue_download',
            help=_('resume downloading a partially-downloaded file'),
        )
        group.add_argument(
            '--progress',
            metavar='TYPE',
            choices=['dot', 'bar'],
            default='bar',
            help=_('choose the type of progress indicator'),
        )
        clobber_group.add_argument(
            '-N',
            '--timestamping',
            action='store_true',
            help=_('only download files that are newer than local files'),
        )
        group.add_argument(
            '--no-use-server-timestamps',
            dest='use_server_timestamps',
            action='store_false',
            default=True,
            help=_('don’t set the last-modified time on files'),
        )
        group.add_argument(
            '-S',
            '--server-response',
            action='store_true',
            help=_('print the protocol responses from the server'),
        )
#         self.add_argument(
#             '--spider',
#             action='store_true',
#             help=_('don’t download but check if URLs exist'),
#         )
        group.add_argument(
            '-T',
            '--timeout',
            metavar='SECONDS',
            type=float,
            help=_('set all timeout options to SECONDS'),
        )
        group.add_argument(
            '--dns-timeout',
            metavar='SECS',
            type=float,
            help=_('timeout after SECS seconds for DNS requests'),
        )
        group.add_argument(
            '--connect-timeout',
            metavar='SECS',
            type=float,
            help=_('timeout after SECS seconds for connection requests'),
        )
        group.add_argument(
            '--read-timeout',
            metavar='SECS',
            default=900,
            type=float,
            help=_('timeout after SECS seconds for reading requests'),
        )
        group.add_argument(
            '-w',
            '--wait',
            metavar='SECONDS',
            type=float,
            default=0.0,
            help=_('wait SECONDS seconds between requests'),
        )
        group.add_argument(
            '--waitretry',
            metavar='SECONDS',
            type=float,
            default=10.0,
            help=_('wait up to SECONDS seconds on retries'),
        )
        group.add_argument(
            '--random-wait',
            action='store_true',
            help=_('randomly perturb the time between requests'),
        )
#         self.add_argument(
#             '--no-proxy',
#             action='store_true',
#             help=_('disable proxy support'),
#         )
        group.add_argument(
            '-Q',
            '--quota',
            metavar='NUMBER',
            type=self.int_bytes,
            help=_('stop after downloading NUMBER bytes'),
        )
        group.add_argument(
            '--bind-address',
            metavar='ADDRESS',
            help=_('bind to ADDRESS on the local host'),
        )
#         self.add_argument(
#             '--limit-rate',
#             metavar='RATE',
#             type=self.int_bytes,
#             help=_('limit download bandwidth to RATE'),
#         )
        group.add_argument(
            '--no-dns-cache',
            action='store_false',
            default=True,
            dest='dns_cache',
            help=_('disable caching of DNS lookups'),
        )
        group.add_argument(
            '--rotate-dns',
            action='store_true',
            help=_('use different resolved IP addresses on requests'),
        )
        group.add_argument(
            '--restrict-file-names',
            metavar='MODES',
            type=self.comma_choice_list,
            choices=CommaChoiceListArgs(
                ['windows', 'unix', 'lower', 'upper', 'ascii', 'nocontrol']
            ),
            default=['windows'] if os.name == 'nt' else ['unix'],
            help=_('list of safe filename modes to use'),
        )
#         self.add_argument(
#             '--ignore-case',
#             action='store_true',
#             help=_('use case-insensitivity on URLs'),
#         )
        inet_group = group.add_mutually_exclusive_group()
        inet_group.add_argument(
            '-4',
            '--inet4-only',
            action='store_const',
            dest='inet_family',
            const='IPv4',
            help=_('connect to IPv4 addresses only'),
        )
        inet_group.add_argument(
            '-6',
            '--inet6-only',
            action='store_const',
            dest='inet_family',
            const='IPv6',
            help=_('connect to IPv6 addresses only'),
        )
        inet_group.add_argument(
            '--prefer-family',
            metavar='FAMILY',
            choices=['IPv6', 'IPv4'],
            help=_('prefer to connect to FAMILY IP addresses'),
        )
#         self.add_argument(
#             '--user'
#         )
#         self.add_argument(
#             '--password'
#         )
#         self.add_argument(
#             '--ask-password',
#             action='store_true',
#         )
        group.add_argument(
            '--no-iri',
            action='store_true',
            help=_('use ASCII encoding only')
        )
        group.add_argument(
            '--local-encoding',
            metavar='ENC',
            help=_('use ENC as the encoding of input files and options')
        )
        group.add_argument(
            '--remote-encoding',
            metavar='ENC',
            help=_('force decoding documents using codec ENC'),
        )
#         self.add_argument(
#             '--unlink'
#         )
        group.add_argument(
            '--max-filename-length',
            metavar='NUMBER',
            default=160,
            type=int,
            help=_('limit filename length to NUMBER characters'),
        )

    def _add_directories_args(self):
        group = self.add_argument_group(_('directories'))
        dir_group = group.add_mutually_exclusive_group()
        dir_group.add_argument(
            '-nd',
            '--no-directories',
            action='store_const',
            const='no',
            dest='use_directories',
            help=_('don’t create directories'),
        )
        dir_group.add_argument(
            '-x',
            '--force-directories',
            action='store_const',
            const='force',
            dest='use_directories',
            help=_('always create directories'),
        )
        group.add_argument(
            '-nH',
            '--no-host-directories',
            dest='host_directories',
            action='store_false',
            default=True,
            help=_('don’t create directories for hostnames')
        )
        group.add_argument(
            '--protocol-directories',
            action='store_true',
            help=_('create directories for URL schemes'),
        )
        group.add_argument(
            '-P',
            '--directory-prefix',
            metavar='PREFIX',
            default=os.curdir,
            help=_('save everything under the directory PREFIX'),
        )
        group.add_argument(
            '--cut-dirs',
            metavar='NUMBER',
            type=int,
            help=_('don’t make NUMBER of leading directories'),
        )

    def _add_http_args(self):
        group = self.add_argument_group('HTTP')
#         self.add_argument(
#             '--http-user',
#         )
#         self.add_argument(
#             '--http-password'
#         )
#         self.add_argument(
#             '--no-cache',
#             action='store_true',
#         )
        group.add_argument(
            '--default-page',
            metavar='NAME',
            default='index.html',
            help=_('use NAME as index page if not known'),
        )
#         self.add_argument(
#             '-E',
#             '--adjust-extension',
#             action='store_true',
#         )
        group.add_argument(
            '--ignore-length',
            action='store_true',
            help=_('ignore any Content-Length provided by the server')
        )
        group.add_argument(
            '--header',
            metavar='STRING',
            default=[],
            action='append',
            help=_('adds STRING to the HTTP header')
        )
        group.add_argument(
            '--max-redirect',
            metavar='NUMBER',
            type=int,
            help=_('follow only up to NUMBER document redirects'),
            default=20,
        )
#         self.add_argument(
#             '--proxy-user',
#             metavar='USER'
#         )
#         self.add_argument(
#             '--proxy-password',
#             metavar='PASS'
#         )
        group.add_argument(
            '--referer',
            metavar='URL',
            help=_('always use URL as the referrer'),
        )
        group.add_argument(
            '--save-headers',
            action='store_true',
            help=_('include server header responses in files'),
        )
        group.add_argument(
            '-U',
            '--user-agent',
            metavar='AGENT',
            help=_('use AGENT instead of Wpull’s user agent'),
        )
        group.add_argument(
            '--no-robots',
            dest='robots',
            action='store_false',
            default=True,
            help=_('ignore robots.txt directives'),
        )
        group.add_argument(
            '--no-http-keep-alive',
            dest='http_keep_alive',
            action='store_false',
            default=True,
            help=_('disable persistent HTTP connections')
        )
        group.add_argument(
            '--no-cookies',
            dest='cookies',
            default=True,
            action='store_false',
            help=_('disables HTTP cookie support')
        )
        group.add_argument(
            '--load-cookies',
            metavar='FILE',
            help=_('load Mozilla cookies.txt from FILE'),
        )
        group.add_argument(
            '--save-cookies',
            metavar='FILE',
            help=_('save Mozilla cookies.txt to FILE'),
        )
        group.add_argument(
            '--keep-session-cookies',
            action='store_true',
            help=_('include session cookies when saving cookies to file')
        )
        post_group = group.add_mutually_exclusive_group()
        post_group.add_argument(
            '--post-data',
            metavar='STRING',
            help=_('use POST for all requests with query STRING'),
        )
        post_group.add_argument(
            '--post-file',
            metavar='FILE',
            type=argparse.FileType('r'),
            help=_('use POST for all requests with query in FILE')
        )
#         self.add_argument(
#             '--method',
#             metavar='HTTPMethod',
#         )
#         self.add_argument(
#             '--body-data',
#             metavar='STRING',
#         )
#         self.add_argument(
#             '--body-file',
#             metavar='FILE'
#         )
#         self.add_argument(
#             '--content-disposition'
#         )
        group.add_argument(
            '--content-on-error',
            action='store_true',
            help=_('keep error pages')
        )
#         self.add_argument(
#             '--auth-no-challenge'
#         )
        group.add_argument(
            '--http-compression',
            action='store_true',
            help=_('request servers to use HTTP compression'),
        )

    def _add_ssl_args(self):
        self._ssl_version_map = {
            'auto': ssl.PROTOCOL_SSLv23,
            'SSLv3': ssl.PROTOCOL_SSLv3,
            'TLSv1': ssl.PROTOCOL_TLSv1,
        }

        if hasattr(ssl, 'PROTOCOL_SSLv2'):
            self._ssl_version_map['SSLv2'] = ssl.PROTOCOL_SSLv2,

        group = self.add_argument_group('SSL')
        group.add_argument(
            '--secure-protocol',
            metavar='PR',
            default='auto',
            choices=sorted(self._ssl_version_map),
            help=_('specify the version of the SSL protocol to use'),
        )
        group.add_argument(
            '--https-only',
            action='store_true',
            help=_('download only HTTPS URLs')
        )
        group.add_argument(
            '--no-check-certificate',
            dest='check_certificate',
            action='store_false',
            default=True,
            help=_('don’t validate SSL server certificates'),
        )
        group.add_argument(
            '--certificate',
            metavar='FILE',
            help=_('use FILE containing the local client certificate')
        )
        group.add_argument(
            '--certificate-type',
            metavar='TYPE',
            choices=['PEM'],
        )
        group.add_argument(
            '--private-key',
            metavar='FILE',
            help=_('use FILE containing the local client private key')
        )
        group.add_argument(
            '--private-key-type',
            metavar='TYPE',
            choices=['PEM'],
        )
        group.add_argument(
            '--ca-certificate',
            metavar='FILE',
            default='/etc/ssl/certs/ca-certificates.crt',
            help=_('load and use CA certificate bundle from FILE'),
        )
        group.add_argument(
            '--ca-directory',
            metavar='DIR',
            default='/etc/ssl/certs/',
            help=_('load and use CA certificates from DIR'),
        )
        group.add_argument(
            '--no-use-internal-ca-certs',
            action='store_false',
            dest='use_internal_ca_certs',
            help=_('don’t use CA certificates included with Wpull')
        )
        group.add_argument(
            '--random-file',
            metavar='FILE',
            help=_('use data from FILE to seed the SSL PRNG')
        )
        group.add_argument(
            '--edg-file',
            metavar='FILE',
            help=_('connect to entropy gathering daemon using socket FILE')
        )

    def _add_ftp_args(self):
        pass
#         self.add_argument(
#             '--ftp-user',
#             metavar='USER'
#         )
#         self.add_argument(
#             '--ftp-password',
#             metavar='PASS'
#         )
#         self.add_argument(
#             '--no-remove-listing',
#             action='store_true',
#         )
#         self.add_argument(
#             '--no-glob',
#             action='store_true',
#         )
#         self.add_argument(
#             '--no-passive-ftp',
#             action='store_true',
#         )
#         self.add_argument(
#             '--preserve-permissions',
#             action='store_true',
#         )
#         self.add_argument(
#             '--retr-symlinks',
#             action='store_true',
#         )

    def _add_warc_args(self):
        group = self.add_argument_group('WARC')
        group.add_argument(
            '--warc-file',
            metavar='FILENAME',
            help=_('save WARC file to filename prefixed with FILENAME'),
        )
        group.add_argument(
            '--warc-append',
            action='store_true',
            help=_('append instead of overwrite the output WARC file')
        )
        group.add_argument(
            '--warc-header',
            metavar='STRING',
            action='append',
            default=[],
            help=_('include STRING in WARC file metadata'),
        )
        group.add_argument(
            '--warc-max-size',
            type=self.int_bytes,
            metavar='NUMBER',
            help=_('write sequential WARC files sized about NUMBER bytes')
        )
        group.add_argument(
            '--warc-cdx',
            action='store_true',
            help=_('write CDX file along with the WARC file')
        )
        group.add_argument(
            '--warc-dedup',
            metavar='FILE',
            type=argparse.FileType('rb'),
            help=_('write revisit records using digests in FILE')
        )
        group.add_argument(
            '--no-warc-compression',
            action='store_true',
            help=_('do not compress the WARC file'),
        )
        group.add_argument(
            '--no-warc-digests',
            action='store_false',
            dest='warc_digests',
            default=True,
            help=_('do not compute and save SHA1 hash digests')
        )
        group.add_argument(
            '--no-warc-keep-log',
            action='store_false',
            dest='warc_log',
            default=True,
            help=_('do not save a log into the WARC file'),
        )
        group.add_argument(
            '--warc-tempdir',
            metavar='DIRECTORY',
            default=os.curdir,
            help=_('use temporary DIRECTORY for preparing WARC files'),
        )

    def _add_recursive_args(self):
        group = self.add_argument_group(_('recursion'))
        group.add_argument(
            '-r',
            '--recursive',
            action='store_true',
            help=_('follow links and download them'),
        )
        group.add_argument(
            '-l',
            '--level',
            metavar='NUMBER',
            type=self.int_0_inf,
            default=5,
            help=_('limit recursion depth to NUMBER')
        )
        group.add_argument(
            '--delete-after',
            action='store_true',
            help=_('download files temporarily and delete them after'),
        )
        group.add_argument(
            '-k',
            '--convert-links',
            action='store_true',
            help=_('rewrite links in files that point to local files')
        )
        group.add_argument(
            '-K',
            '--backup-converted',
            action='store_true',
            help=_('save original files before converting their links')
        )
#         self.add_argument(
#             '-m',
#             '--mirror',
#             action='store_true',
#             help=_('use options "-N -r -l inf --no-remove-listing"')
#         )
        group.add_argument(
            '-p',
            '--page-requisites',
            action='store_true',
            help=_('download objects embedded in pages')
        )
#         self.add_argument(
#             '--strict-comments',
#             action='store_true',
#             help=_('use strict SGML comment parsing')
#         )
        group.add_argument(
            '--sitemaps',
            action='store_true',
            help=_('download Sitemaps to discover more links')
        )

    def _add_accept_args(self):
        group = self.add_argument_group(_('filters'))
        group.add_argument(
            '-A',
            '--accept',
            metavar='LIST',
            type=self.comma_list,
            help=_('download only files with suffix in LIST'),
        )
        group.add_argument(
            '-R',
            '--reject',
            metavar='LIST',
            help=_('don’t download files with suffix in LIST'),
        )
        group.add_argument(
            '--accept-regex',
            metavar='REGEX',
            help=_('download only URLs matching REGEX'),
        )
        group.add_argument(
            '--reject-regex',
            metavar='REGEX',
            help=_('don’t download URLs matching REGEX'),
        )
        group.add_argument(
            '--regex-type',
            metavar='TYPE',
            choices=['posix'],
            help=_('use regex TYPE')
        )
        group.add_argument(
            '-D',
            '--domains',
            metavar='LIST',
            type=self.comma_list,
            help=_('download only from LIST of hostname suffixes')
        )
        group.add_argument(
            '--exclude-domains',
            metavar='LIST',
            type=self.comma_list,
            help=_('don’t download from LIST of hostname suffixes')
        )
        group.add_argument(
            '--hostnames',
            metavar='LIST',
            type=self.comma_list,
            help=_('download only from LIST of hostnames')
        )
        group.add_argument(
            '--exclude-hostnames',
            metavar='LIST',
            type=self.comma_list,
            help=_('don’t download from LIST of hostnames')
        )
#         self.add_argument(
#             '--follow-ftp',
#             action='store_true',
#             help=_('follow links to FTP sites')
#         )
        group.add_argument(
            '--follow-tags',
            metavar='LIST',
            type=self.comma_list,
            help=_('follow only links contained in LIST of HTML tags'),
        )
        group.add_argument(
            '--ignore-tags',
            metavar='LIST',
            type=self.comma_list,
            help=_('don’t follow links contained in LIST of HTML tags'),
        )
        span_hosts_group = group.add_mutually_exclusive_group()
        span_hosts_group.add_argument(
            '-H',
            '--span-hosts',
            action='store_true',
            help=_('follow links and page requisites to other hostnames')
        )
        span_hosts_group.add_argument(
            '--span-hosts-allow',
            metavar='LIST',
            choices=CommaChoiceListArgs(['page-requisites', 'linked-pages']),
            type=self.comma_choice_list,
            default=[],
            help=_('selectively span hosts for resource types in LIST')
        )
        group.add_argument(
            '-L',
            '--relative',
            action='store_true',
            help=_('follow only relative links')
        )
        group.add_argument(
            '-I',
            '--include-directories',
            metavar='LIST',
            type=self.comma_list,
            help=_('download only paths in LIST')
        )
#         self.add_argument(
#             '--trust-server-names',
#             action='store_true',
#             help=_('use the last given filename by the server for filenames')
#         )
        group.add_argument(
            '-X',
            '--exclude-directories',
            metavar='LIST',
            type=self.comma_list,
            help=_('don’t download paths in LIST')
        )
        group.add_argument(
            '-np',
            '--no-parent',
            action='store_true',
            help=_('don’t follow to parent directories on URL path'),
        )
        group.add_argument(
            '--no-strong-robots',
            dest='strong_robots',
            action='store_false',
            default=True,
            help=_('don’t ignore filters for robots.txt'),
        )
        group.add_argument(
            '--no-strong-redirects',
            dest='strong_redirects',
            action='store_false',
            default=True,
            help=_('don’t implicitly allow span hosts for redirects'),
        )

    def _add_phantomjs_args(self):
        group = self.add_argument_group(_('PhantomJS'))
        group.add_argument(
            '--phantomjs',
            action='store_true',
            help=_('use PhantomJS for loading dynamic pages'),
        )
        group.add_argument(
            '--phantomjs-scroll',
            type=int,
            default=10,
            metavar='NUM',
            help=_('scroll the page up to NUM times'),
        )
        group.add_argument(
            '--phantomjs-wait',
            type=float,
            default=1.0,
            metavar='SEC',
            help=_('wait SEC seconds between page interactions'),
        )
        group.add_argument(
            '--no-phantomjs-snapshot',
            action='store_false',
            dest='phantomjs_snapshot',
            default=True,
            help=_('don’t take dynamic page snapshots'),
        )
        group.add_argument(
            '--no-phantomjs-smart-scroll',
            action='store_false',
            dest='phantomjs_smart_scroll',
            default=True,
            help=_('always scroll the page to maximum scroll count option'),
        )

    def _post_parse_args(self, args):
        if args.warc_file:
            self._post_warc_args(args)

        if not args.input_file and not args.urls:
            self.error(_('no URL provided'))

        self._post_ssl_args(args)

        if not args.recursive:
            args.robots = False

        if args.no_iri and (args.local_encoding or args.remote_encoding):
            self.error(_('disabling IRI support forces use of ASCII encoding'))
        elif args.no_iri:
            args.local_encoding = 'ascii'
            args.remote_encoding = 'ascii'

        if not args.verbosity:
            args.verbosity = logging.INFO

    def _post_warc_args(self, args):
        option_names = ('clobber_method', 'timestamping', 'continue_download')

        for option_name in option_names:
            if vars(args).get(option_name):
                self.error(
                    _('WARC output cannot be combined with {option_name}.') \
                        .format(option_name=option_name)
                )

    def _post_ssl_args(self, args):
        if args.secure_protocol:
            args.secure_protocol = self._ssl_version_map[args.secure_protocol]

        if args.certificate and not os.path.exists(args.certificate):
            self.error(_('certificate file not found'))

        if args.private_key and not os.path.exists(args.private_key):
            self.error(_('private key file not found'))
