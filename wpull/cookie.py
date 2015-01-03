# encoding=utf-8
'''HTTP Cookies.'''
import gettext
from http.cookiejar import DefaultCookiePolicy, MozillaCookieJar
import logging
import re

import wpull.util

_logger = logging.getLogger(__name__)


class DeFactoCookiePolicy(DefaultCookiePolicy):
    '''Cookie policy that limits the content and length of the cookie.

    Args:
        cookie_jar: The CookieJar instance.

    This policy class is *not* designed to be shared between CookieJar
    instances.
    '''
    def __init__(self, *args, **kwargs):
        self.cookie_jar = kwargs.pop('cookie_jar')
        DefaultCookiePolicy.__init__(self, *args, **kwargs)

    def set_ok(self, cookie, request):
        if not DefaultCookiePolicy.set_ok(self, cookie, request):
            return False

        try:
            new_cookie_length = (self.cookie_length(cookie.domain) +
                                 len(cookie.path) + len(cookie.name) +
                                 len(cookie.value or ''))
        except TypeError as error:
            # cookiejar is not infallible #220
            _logger.debug('Cookie handling error', exc_info=1)
            return False

        if new_cookie_length >= 4100:
            return False

        if self.count_cookies(cookie.domain) >= 50:
            cookies = self.cookie_jar._cookies
            try:
                cookies[cookie.domain][cookie.path][cookie.name]
            except KeyError:
                return False

        if not wpull.util.is_ascii(str(cookie)):
            return False

        return True

    def count_cookies(self, domain):
        '''Return the number of cookies for the given domain.'''
        cookies = self.cookie_jar._cookies

        if domain in cookies:
            return sum(
                [len(cookie) for cookie in cookies[domain].values()]
            )
        else:
            return 0

    def cookie_length(self, domain):
        '''Return approximate length of all cookie key-values for a domain.'''
        cookies = self.cookie_jar._cookies

        if domain not in cookies:
            return 0

        length = 0

        for path in cookies[domain]:
            for name in cookies[domain][path]:
                cookie = cookies[domain][path][name]
                length += len(path) + len(name) + len(cookie.value or '')

        return length


class RelaxedMozillaCookieJar(MozillaCookieJar):
    '''MozillaCookieJar that ignores file header checks.'''
    magic_re = re.compile(r'.')
