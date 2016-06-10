'''Fetching rules.'''
import asyncio
import logging
import random

from typing import Optional, Tuple

import wpull.url
from wpull.application.plugin import PluginFunctions, hook_interface, \
    event_interface
from wpull.scraper.base import DemuxDocumentScraper, BaseScraper, ScrapeResult
from wpull.stats import Statistics
from wpull.url import URLInfo
from wpull.backport.logging import StyleAdapter
from wpull.errors import DNSNotFound, ServerError, ConnectionRefused, \
    SSLVerificationError, ProtocolError
from wpull.application.hook import HookableMixin, HookDisconnected, Actions, HookStop
from wpull.pipeline.item import Status, URLRecord
from wpull.pipeline.session import ItemSession
import wpull.application.hook
from wpull.protocol.http.robots import RobotsTxtChecker
from wpull.urlfilter import DemuxURLFilter
from wpull.protocol.http.request import Request as HTTPRequest
from wpull.urlrewrite import URLRewriter
from wpull.waiter import Waiter

_logger = StyleAdapter(logging.getLogger(__name__))


class FetchRule(HookableMixin):
    '''Decide on what URLs should be fetched.'''
    def __init__(self, url_filter: DemuxURLFilter=None,
                 robots_txt_checker: RobotsTxtChecker=None,
                 http_login: Optional[Tuple[str, str]]=None,
                 ftp_login: Optional[Tuple[str, str]]=None,
                 duration_timeout: Optional[int]=None):
        super().__init__()
        self._url_filter = url_filter
        self._robots_txt_checker = robots_txt_checker
        self.http_login = http_login
        self.ftp_login = ftp_login
        self.duration_timeout = duration_timeout

        self.hook_dispatcher.register(PluginFunctions.accept_url)

    @asyncio.coroutine
    def consult_robots_txt(self, request: HTTPRequest) -> bool:
        '''Consult by fetching robots.txt as needed.

        Args:
            request: The request to be made
                to get the file.

        Returns:
            True if can fetch

        Coroutine
        '''
        if not self._robots_txt_checker:
            return True

        result = yield from self._robots_txt_checker.can_fetch(request)
        return result

    def consult_helix_fossil(self) -> bool:
        '''Consult the helix fossil.

        Returns:
            True if can fetch
        '''

        return random.random() < 0.75

    def consult_filters(self, url_info: URLInfo, url_record: URLRecord, is_redirect: bool=False) \
            -> Tuple[bool, str, dict]:
        '''Consult the URL filter.

        Args:
            url_record: The URL record.
            is_redirect: Whether the request is a redirect and it is
                desired that it spans hosts.

        Returns
            tuple:

            1. bool: The verdict
            2. str: A short reason string: nofilters, filters, redirect
            3. dict: The result from :func:`DemuxURLFilter.test_info`
        '''
        if not self._url_filter:
            return True, 'nofilters', None

        test_info = self._url_filter.test_info(url_info, url_record)

        verdict = test_info['verdict']

        if verdict:
            reason = 'filters'
        elif is_redirect and self.is_only_span_hosts_failed(test_info):
            verdict = True
            reason = 'redirect'
        else:
            reason = 'filters'

        return verdict, reason, test_info

    @classmethod
    def is_only_span_hosts_failed(cls, test_info: dict) -> bool:
        '''Return whether only the SpanHostsFilter failed.'''
        return (
            len(test_info['failed']) == 1 and
            'SpanHostsFilter' in test_info['map'] and
            not test_info['map']['SpanHostsFilter']
            )

    def consult_hook(self, item_session: ItemSession, verdict: bool,
                     reason: str, test_info: dict):
        '''Consult the scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        try:
            reasons = {
                'filters': test_info['map'],
                'reason': reason,
            }

            verdict = self.hook_dispatcher.call(
                PluginFunctions.accept_url, item_session, verdict, reasons,
            )
            reason = 'callback_hook'
        except HookDisconnected:
            pass

        return verdict, reason

    @staticmethod
    @hook_interface(PluginFunctions.accept_url)
    def plugin_accept_url(item_session: ItemSession, verdict: bool, reasons: dict) -> bool:
        '''Return whether to download this URL.

        Args:
            item_session: Current URL item.
            verdict: A bool indicating whether Wpull wants to download
                the URL.
            reasons: A dict containing information for the verdict:

                * ``filters`` (dict): A mapping (str to bool) from filter name
                  to whether the filter passed or not.
                * ``reason`` (str): A short reason string. Current values are:
                  ``filters``, ``robots``, ``redirect``.

        Returns:
            If ``True``, the URL should be downloaded. Otherwise, the URL
            is skipped.
        '''
        return verdict

    @asyncio.coroutine
    def check_initial_web_request(self, item_session: ItemSession, request: HTTPRequest) -> Tuple[bool, str]:
        '''Check robots.txt, URL filters, and scripting hook.

        Returns:
            tuple: (bool, str)

        Coroutine.
        '''
        verdict, reason, test_info = self.consult_filters(item_session.request.url_info, item_session.url_record)

        if verdict and self._robots_txt_checker:
            can_fetch = yield from self.consult_robots_txt(request)

            if not can_fetch:
                verdict = False
                reason = 'robotstxt'

        verdict, reason = self.consult_hook(
            item_session, verdict, reason, test_info
        )

        return verdict, reason

    def check_subsequent_web_request(self, item_session: ItemSession,
                                     is_redirect: bool=False) -> Tuple[bool, str]:
        '''Check URL filters and scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        verdict, reason, test_info = self.consult_filters(
            item_session.request.url_info,
            item_session.url_record, is_redirect=is_redirect)

        # TODO: provide an option to change this
        if item_session.is_virtual:
            verdict = True

        verdict, reason = self.consult_hook(item_session, verdict,
                                            reason, test_info)

        return verdict, reason

    def check_generic_request(self, item_session: ItemSession) -> Tuple[bool, str]:
        '''Check URL filters and scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        verdict, reason, test_info = self.consult_filters(
            item_session.request.url_info,
            item_session.url_record)

        verdict, reason = self.consult_hook(item_session, verdict,
                                            reason, test_info)

        return verdict, reason

    check_ftp_request = check_generic_request


class ResultRule(HookableMixin):
    '''Decide on the results of a fetch.

    Args:
        ssl_verification: If True, don't ignore certificate errors.
        retry_connrefused: If True, don't consider a connection refused
            error to be a permanent error.
        retry_dns_error: If True, don't consider a DNS resolution error
            to be permanent error.
        waiter: The Waiter.
        statistics: The Statistics.
    '''
    def __init__(self, ssl_verification: bool=False,
                 retry_connrefused: bool=False,
                 retry_dns_error: bool=False,
                 waiter: Optional[Waiter]=None,
                 statistics: Optional[Statistics]=None):
        super().__init__()
        self._ssl_verification = ssl_verification
        self.retry_connrefused = retry_connrefused
        self.retry_dns_error = retry_dns_error
        self._waiter = waiter
        self._statistics = statistics

        self.hook_dispatcher.register(PluginFunctions.wait_time)
        self.hook_dispatcher.register(PluginFunctions.handle_response)
        self.hook_dispatcher.register(PluginFunctions.handle_pre_response)
        self.hook_dispatcher.register(PluginFunctions.handle_error)

    def handle_pre_response(self, item_session: ItemSession) -> Actions:
        '''Process a response that is starting.'''
        action = self.consult_pre_response_hook(item_session)

        if action == Actions.RETRY:
            item_session.set_status(Status.skipped)
        elif action == Actions.FINISH:
            item_session.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')

        return action

    def handle_document(self, item_session: ItemSession, filename: str) -> Actions:
        '''Process a successful document response.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(item_session)

        if action == Actions.NORMAL:
            self._statistics.increment(item_session.response.body.size())
            item_session.set_status(Status.done, filename=filename)

        return action

    def handle_no_document(self, item_session: ItemSession) -> Actions:
        '''Callback for successful responses containing no useful document.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(item_session)

        if action == Actions.NORMAL:
            item_session.set_status(Status.skipped)

        return action

    def handle_intermediate_response(self, item_session: ItemSession) -> Actions:
        '''Callback for successful intermediate responses.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(item_session)

        return action

    def handle_document_error(self, item_session: ItemSession) -> Actions:
        '''Callback for when the document only describes an server error.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        self._waiter.increment()

        self._statistics.errors[ServerError] += 1

        action = self.handle_response(item_session)

        if action == Actions.NORMAL:
            item_session.set_status(Status.error)

        return action

    def handle_response(self, item_session: ItemSession) -> Actions:
        '''Generic handler for a response.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        action = self.consult_response_hook(item_session)

        if action == Actions.RETRY:
            item_session.set_status(Status.error)
        elif action == Actions.FINISH:
            item_session.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')

        return action

    def handle_error(self, item_session: ItemSession, error: BaseException) -> Actions:
        '''Process an error.

        Returns:
            A value from :class:`.hook.Actions`.
        '''
        if not self._ssl_verification and \
                isinstance(error, SSLVerificationError):
            # Change it into a different error since the user doesn't care
            # about verifying certificates
            self._statistics.increment_error(ProtocolError())
        else:
            self._statistics.increment_error(error)

        self._waiter.increment()

        action = self.consult_error_hook(item_session, error)

        if action == Actions.RETRY:
            item_session.set_status(Status.error)
        elif action == Actions.FINISH:
            item_session.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')
        elif self._ssl_verification and isinstance(error, SSLVerificationError):
            raise
        elif isinstance(error, ConnectionRefused) and \
                not self.retry_connrefused:
            item_session.set_status(Status.skipped)
        elif isinstance(error, DNSNotFound) and \
                not self.retry_dns_error:
            item_session.set_status(Status.skipped)
        else:
            item_session.set_status(Status.error)

        return action

    def get_wait_time(self, item_session: ItemSession, error=None):
        '''Return the wait time in seconds between requests.'''
        seconds = self._waiter.get()
        try:
            return self.hook_dispatcher.call(PluginFunctions.wait_time, seconds,
                                             item_session, error)
        except HookDisconnected:
            return seconds

    @staticmethod
    @hook_interface(PluginFunctions.wait_time)
    def plugin_wait_time(seconds: float, item_session: ItemSession, error: Optional[Exception]=None) -> float:
        '''Return the wait time between requests.

        Args:
            seconds: The original time in seconds.
            item_session:
            error:

        Returns:
            The time in seconds.
        '''
        return seconds

    def consult_pre_response_hook(self, item_session: ItemSession) -> Actions:
        '''Return scripting action when a response begins.'''
        try:
            return self.hook_dispatcher.call(
                PluginFunctions.handle_pre_response,
                item_session
            )
        except HookDisconnected:
            return Actions.NORMAL

    @staticmethod
    @hook_interface(PluginFunctions.handle_pre_response)
    def plugin_handle_pre_response(item_session: ItemSession) -> Actions:
        '''Return an action to handle a response status before a download.

        Args:
            item_session:

        Returns:
            A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL

    def consult_response_hook(self, item_session: ItemSession) -> Actions:
        '''Return scripting action when a response ends.'''
        try:
            return self.hook_dispatcher.call(
                PluginFunctions.handle_response, item_session
            )
        except HookDisconnected:
            return Actions.NORMAL

    @staticmethod
    @hook_interface(PluginFunctions.handle_response)
    def plugin_handle_response(item_session: ItemSession) -> Actions:
        '''Return an action to handle the response.

        Args:
            item_session:

        Returns:
            A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL

    def consult_error_hook(self, item_session: ItemSession, error: BaseException):
        '''Return scripting action when an error occured.'''
        try:
            return self.hook_dispatcher.call(
                PluginFunctions.handle_error, item_session, error)
        except HookDisconnected:
            return Actions.NORMAL

    @staticmethod
    @hook_interface(PluginFunctions.handle_error)
    def plugin_handle_error(item_session: ItemSession, error: BaseException) -> Actions:
        '''Return an action to handle the error.

        Args:
            item_session:
            error:

        Returns:
            A value from :class:`Actions`. The default is
            :attr:`Actions.NORMAL`.
        '''
        return Actions.NORMAL


class ProcessingRule(HookableMixin):
    '''Document processing rules.

    Args:
        fetch_rule: The FetchRule instance.
        document_scraper: The document
            scraper.
    '''
    def __init__(self, fetch_rule: FetchRule,
                 document_scraper: DemuxDocumentScraper=None,
                 sitemaps: bool=False,
                 url_rewriter: URLRewriter=None):
        super().__init__()

        self._fetch_rule = fetch_rule
        self._document_scraper = document_scraper
        self._sitemaps = sitemaps
        self._url_rewriter = url_rewriter

        self.event_dispatcher.register(PluginFunctions.get_urls)

    parse_url = staticmethod(wpull.url.parse_url_or_log)

    def add_extra_urls(self, item_session: ItemSession):
        '''Add additional URLs such as robots.txt, favicon.ico.'''

        if item_session.url_record.level == 0 and self._sitemaps:
            extra_url_infos = (
                self.parse_url(
                    '{0}://{1}/robots.txt'.format(
                        item_session.url_record.url_info.scheme,
                        item_session.url_record.url_info.hostname_with_port)
                ),
                self.parse_url(
                    '{0}://{1}/sitemap.xml'.format(
                        item_session.url_record.url_info.scheme,
                        item_session.url_record.url_info.hostname_with_port)
                )
            )

            for url_info in extra_url_infos:
                item_session.add_child_url(url_info.url)

    def scrape_document(self, item_session: ItemSession):
        '''Process document for links.'''
        self.event_dispatcher.notify(
            PluginFunctions.get_urls, item_session
        )

        if not self._document_scraper:
            return

        demux_info = self._document_scraper.scrape_info(
            item_session.request, item_session.response,
            item_session.url_record.link_type
        )

        num_inline_urls = 0
        num_linked_urls = 0

        for scraper, scrape_result in demux_info.items():
            new_inline, new_linked = self._process_scrape_info(
                scraper, scrape_result, item_session
            )
            num_inline_urls += new_inline
            num_linked_urls += new_linked

        _logger.debug('Candidate URLs: inline={0} linked={1}',
                      num_inline_urls, num_linked_urls
        )

    @staticmethod
    @event_interface(PluginFunctions.get_urls)
    def plugin_get_urls(item_session: ItemSession):
        '''Add additional URLs to be added to the URL Table.

        When this event is dispatched, the caller should add any URLs needed
        using :meth:`.ItemSession.add_child_url`.
        '''

    def _process_scrape_info(self, scraper: BaseScraper,
                             scrape_result: ScrapeResult,
                             item_session: ItemSession):
        '''Collect the URLs from the scrape info dict.'''
        if not scrape_result:
            return 0, 0

        num_inline = 0
        num_linked = 0

        for link_context in scrape_result.link_contexts:
            url_info = self.parse_url(link_context.link)

            if not url_info:
                continue

            url_info = self.rewrite_url(url_info)

            child_url_record = item_session.child_url_record(
                url_info.url, inline=link_context.inline
            )
            if not self._fetch_rule.consult_filters(item_session.request.url_info, child_url_record)[0]:
                continue

            if link_context.inline:
                num_inline += 1
            else:
                num_linked += 1

            item_session.add_child_url(url_info.url, inline=link_context.inline,
                                       link_type=link_context.link_type)

        return num_inline, num_linked

    def rewrite_url(self, url_info: URLInfo) -> URLInfo:
        '''Return a rewritten URL such as escaped fragment.'''
        if self._url_rewriter:
            return self._url_rewriter.rewrite(url_info)
        else:
            return url_info
