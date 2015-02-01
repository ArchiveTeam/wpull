'''Fetching rules.'''
import logging
import random

from trollius import From, Return
import trollius

from wpull.backport.logging import BraceMessage as __
from wpull.hook import HookableMixin, HookDisconnected, Actions, HookStop
from wpull.item import Status, LinkType
from wpull.errors import DNSNotFound, ServerError, ConnectionRefused, \
    SSLVerificationError, ProtocolError
from wpull.scraper.css import CSSScraper
from wpull.scraper.html import HTMLScraper
import wpull.url


_logger = logging.getLogger(__name__)


class FetchRule(HookableMixin):
    '''Decide on what URLs should be fetched.'''
    def __init__(self, url_filter=None, robots_txt_checker=None,
                 http_login=None, ftp_login=None):
        super().__init__()
        self._url_filter = url_filter
        self._robots_txt_checker = robots_txt_checker
        self.http_login = http_login
        self.ftp_login = ftp_login

        self.register_hook('should_fetch')

    @trollius.coroutine
    def consult_robots_txt(self, request):
        '''Consult by fetching robots.txt as needed.

        Args:
            request (:class:`.http.request.Request`): The request to be made
                to get the file.

        Returns:
            bool

        Coroutine
        '''
        if not self._robots_txt_checker:
            raise Return(True)

        result = yield From(self._robots_txt_checker.can_fetch(request))
        raise Return(result)

    def consult_helix_fossil(self):
        '''Consult the helix fossil.

        Returns:
            bool
        '''

        return random.random() < 0.75

    def consult_filters(self, url_info, url_record, is_redirect=False):
        '''Consult the URL filter.

        Args:
            url_info (URLInfo): The URL info.
            url_record (URLRecord): The URL record.
            is_redirect (bool): Whether the request is a redirect and it is
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
    def is_only_span_hosts_failed(cls, test_info):
        '''Return whether only the SpanHostsFilter failed.'''
        return (
            len(test_info['failed']) == 1 and
            'SpanHostsFilter' in test_info['map'] and
            not test_info['map']['SpanHostsFilter']
            )

    def consult_hook(self, url_info, url_record, verdict, reason, test_info):
        '''Consult the scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        try:
            verdict = self.call_hook(
                'should_fetch', url_info, url_record, verdict, reason,
                test_info,
            )
            reason = 'callback_hook'
        except HookDisconnected:
            pass

        return verdict, reason

    @trollius.coroutine
    def check_initial_web_request(self, request, url_record):
        '''Check robots.txt, URL filters, and scripting hook.

        Returns:
            tuple: (bool, str)

        Coroutine.
        '''
        verdict, reason, test_info = self.consult_filters(
            request.url_info, url_record
        )

        if verdict and self._robots_txt_checker:
            can_fetch = yield From(self.consult_robots_txt(request))

            if not can_fetch:
                verdict = False
                reason = 'robotstxt'

        verdict, reason = self.consult_hook(
            request.url_info, url_record, verdict, reason, test_info
        )

        raise Return((verdict, reason))

    def check_subsequent_web_request(self, url_info, url_record,
                                     is_redirect=False):
        '''Check URL filters and scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        verdict, reason, test_info = self.consult_filters(
            url_info, url_record, is_redirect=is_redirect)

        verdict, reason = self.consult_hook(url_info, url_record, verdict,
                                            reason, test_info)

        return verdict, reason

    def check_generic_request(self, url_info, url_record):
        '''Check URL filters and scripting hook.

        Returns:
            tuple: (bool, str)
        '''
        verdict, reason, test_info = self.consult_filters(
            url_info, url_record)

        verdict, reason = self.consult_hook(url_info, url_record, verdict,
                                            reason, test_info)

        return verdict, reason

    check_ftp_request = check_generic_request


class ResultRule(HookableMixin):
    '''Decide on the results of a fetch.

    Args:
        ssl_verification (bool): If True, don't ignore certificate errors.
        retry_connrefused (bool): If True, don't consider a connection refused
            error to be a permanent error.
        retry_dns_error (bool): If True, don't consider a DNS resolution error
            to be permanent error.
        waiter (:class:`.waiter.Waiter`): The Waiter.
        statistics (:class:`.stats.Statistics`): The Statistics.
    '''
    def __init__(self, ssl_verification=False, retry_connrefused=False,
                 retry_dns_error=False, waiter=None, statistics=None):
        super().__init__()
        self._ssl_verification = ssl_verification
        self.retry_connrefused = retry_connrefused
        self.retry_dns_error = retry_dns_error
        self._waiter = waiter
        self._statistics = statistics

        self.register_hook(
            'wait_time', 'handle_response', 'handle_pre_response',
            'handle_error',
        )

    def handle_pre_response(self, request, response, url_item):
        '''Process a response that is starting.'''
        action = self.consult_pre_response_hook(
            request, response, url_item.url_record)

        if action == Actions.RETRY:
            url_item.set_status(Status.skipped)
        elif action == Actions.FINISH:
            url_item.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')

        return action

    def handle_document(self, request, response, url_item, filename):
        '''Process a successful document response.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(request, response, url_item)

        if action == Actions.NORMAL:
            self._statistics.increment(response.body.size())
            url_item.set_status(Status.done, filename=filename)

        return action

    def handle_no_document(self, request, response, url_item):
        '''Callback for successful responses containing no useful document.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(request, response, url_item)

        if action == Actions.NORMAL:
            url_item.set_status(Status.skipped)

        return action

    def handle_intermediate_response(self, request, response, url_item):
        '''Callback for successful intermediate responses.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        self._waiter.reset()

        action = self.handle_response(request, response, url_item)

        return action

    def handle_document_error(self, request, response, url_item):
        '''Callback for when the document only describes an server error.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        self._waiter.increment()

        self._statistics.errors[ServerError] += 1

        action = self.handle_response(request, response, url_item)

        if action == Actions.NORMAL:
            url_item.set_status(Status.error)

        return action

    def handle_response(self, request, response, url_item):
        '''Generic handler for a response.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        action = self.consult_response_hook(
            request, response, url_item.url_record)

        if action == Actions.RETRY:
            url_item.set_status(Status.error)
        elif action == Actions.FINISH:
            url_item.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')

        return action

    def handle_error(self, request, error, url_item):
        '''Process an error.

        Returns:
            str: A value from :class:`.hook.Actions`.
        '''
        if not self._ssl_verification and \
                isinstance(error, SSLVerificationError):
            # Change it into a different error since the user doesn't care
            # about verifying certificates
            self._statistics.increment_error(ProtocolError())
        else:
            self._statistics.increment_error(error)

        self._waiter.increment()

        action = self.consult_error_hook(request, url_item.url_record, error)

        if action == Actions.RETRY:
            url_item.set_status(Status.error)
        elif action == Actions.FINISH:
            url_item.set_status(Status.done)
        elif action == Actions.STOP:
            raise HookStop('Script requested immediate stop.')
        elif self._ssl_verification and isinstance(error, SSLVerificationError):
            raise
        elif isinstance(error, ConnectionRefused) and \
                not self.retry_connrefused:
            url_item.set_status(Status.skipped)
        elif isinstance(error, DNSNotFound) and \
                not self.retry_dns_error:
            url_item.set_status(Status.skipped)
        else:
            url_item.set_status(Status.error)

        return action

    def get_wait_time(self):
        '''Return the wait time in seconds between requests.'''
        seconds = self._waiter.get()
        try:
            return self.call_hook('wait_time', seconds)
        except HookDisconnected:
            return seconds

    def consult_pre_response_hook(self, request, response, url_record):
        '''Return scripting action when a response begins.'''
        try:
            return self.call_hook(
                'handle_pre_response', request, response, url_record
            )
        except HookDisconnected:
            return Actions.NORMAL

    def consult_response_hook(self, request, response, url_record):
        '''Return scripting action when a response ends.'''
        try:
            return self.call_hook(
                'handle_response', request, response, url_record
            )
        except HookDisconnected:
            return Actions.NORMAL

    def consult_error_hook(self, request, url_record, error):
        '''Return scripting action when an error occured.'''
        try:
            return self.call_hook('handle_error', request, url_record, error)
        except HookDisconnected:
            return Actions.NORMAL


class ProcessingRule(HookableMixin):
    '''Document processing rules.

    Args:
        fetch_rule (FetchRule): The FetchRule instance.
        document_scraper (:class:`.scaper.DemuxDocumentScraper`): The document
            scraper.
    '''
    def __init__(self, fetch_rule, document_scraper=None, sitemaps=False, url_rewriter=None):
        super().__init__()

        self._fetch_rule = fetch_rule
        self._document_scraper = document_scraper
        self._sitemaps = sitemaps
        self._url_rewriter = url_rewriter

        self.register_hook('scrape_document')

    parse_url = staticmethod(wpull.url.parse_url_or_log)

    def add_extra_urls(self, url_item):
        '''Add additional URLs such as robots.txt, favicon.ico.'''

        if url_item.url_record.level == 0 and self._sitemaps:
            extra_url_infos = (
                self.parse_url(
                    '{0}://{1}/robots.txt'.format(
                        url_item.url_info.scheme,
                        url_item.url_info.hostname_with_port)
                ),
                self.parse_url(
                    '{0}://{1}/sitemap.xml'.format(
                        url_item.url_info.scheme,
                        url_item.url_info.hostname_with_port)
                )
            )

            url_item.add_child_urls(
                [url_info.url for url_info in extra_url_infos]
            )

    def scrape_document(self, request, response, url_item):
        '''Process document for links.'''
        try:
            self.call_hook(
                'scrape_document', request, response, url_item
            )
        except HookDisconnected:
            pass

        if not self._document_scraper:
            return

        demux_info = self._document_scraper.scrape_info(
            request, response, url_item.url_record.link_type
        )

        num_inline_urls = 0
        num_linked_urls = 0

        for scraper, scrape_result in demux_info.items():
            new_inline, new_linked = self._process_scrape_info(
                scraper, scrape_result, url_item
            )
            num_inline_urls += new_inline
            num_linked_urls += new_linked

        _logger.debug(__('Candidate URLs: inline={0} linked={1}',
                         num_inline_urls, num_linked_urls
        ))

    def _process_scrape_info(self, scraper, scrape_result, url_item):
        '''Collect the URLs from the scrape info dict.'''
        if not scrape_result:
            return 0, 0

        urls_to_be_added = []
        num_inline = 0
        num_linked = 0

        for link_context in scrape_result.link_contexts:
            url_info = self.parse_url(link_context.link)

            if url_info:
                url_info = self.rewrite_url(url_info)
                url_record = url_item.child_url_record(
                    url_info, inline=link_context.inline
                )
                if self._fetch_rule.check_generic_request(url_info, url_record)[0]:
                    urls_to_be_added.append({
                        'url': url_info.url,
                        'inline': link_context.inline,
                        'link_type': link_context.link_type
                    })
                    if link_context.inline:
                        num_inline += 1
                    else:
                        num_linked += 1

        url_item.add_child_urls(urls_to_be_added)

        return num_inline, num_linked

    def rewrite_url(self, url_info):
        '''Return a rewritten URL such as escaped fragment.'''
        if self._url_rewriter:
            return self._url_rewriter.rewrite(url_info)
        else:
            return url_info
