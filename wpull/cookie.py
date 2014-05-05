# encoding=utf-8
'''HTTP Cookies.'''
from http.cookiejar import DefaultCookiePolicy, MozillaCookieJar
import re


class CookieLimitsPolicy(DefaultCookiePolicy):
    '''Cookie policy that limits the length of the cookie.

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

        if len(repr(cookie)) > 4100:
            return False

        if self.count_cookies(cookie.domain) >= 50:
            cookies = self.cookie_jar._cookies
            try:
                cookies[cookie.domain][cookie.path][cookie.name]
            except KeyError:
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


class RelaxedMozillaCookieJar(MozillaCookieJar):
    '''MozillaCookieJar that ignores file header checks.'''
    magic_re = re.compile(r'.')
