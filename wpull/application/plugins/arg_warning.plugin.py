import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.application.plugin import WpullPlugin

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class ArgWarningPlugin(WpullPlugin):
    UNSAFE_OPTIONS = frozenset(['save_headers', 'no_iri', 'output_document',
                                'ignore_fatal_errors'])

    def activate(self):
        super().activate()
        self._warn_unsafe_options(self.app_session.args)
        self._warn_silly_options(self.app_session.args)

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

