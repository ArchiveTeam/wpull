# encoding=utf-8
'''HTTP Cookies.'''
from http.cookiejar import DefaultCookiePolicy
import http.cookiejar
import logging
import re
import time
import io
import traceback
import warnings

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
        except TypeError:
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


class BetterMozillaCookieJar(http.cookiejar.FileCookieJar):
    '''MozillaCookieJar that is compatible with Wget/Curl.

    It ignores file header checks and supports session cookies.
    '''
    # This class from cpython/Lib/http/cookiejar.py changeset 95436:ea94f6c87f5d
    # Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    # 2011, 2012, 2013, 2014, 2015 Python Software Foundation; All Rights
    # Reserved
    magic_re = re.compile(r'.')
    header = """\
# Netscape HTTP Cookie File
# http://curl.haxx.se/rfc/cookie_spec.html
# This is a generated file!  Do not edit.

"""

    def _really_load(self, f, filename, ignore_discard, ignore_expires):
        now = time.time()

        magic = f.readline()
        if not self.magic_re.search(magic):
            raise http.cookiejar.LoadError(
                "%r does not look like a Netscape format cookies file" %
                filename)

        line = ""
        try:
            while 1:
                line = f.readline()
                if line == "":
                    break

                # last field may be absent, so keep any trailing tab
                if line.endswith("\n"):
                    line = line[:-1]

                # skip comments and blank lines XXX what is $ for?
                if (line.strip().startswith(("#", "$")) or
                        line.strip() == ""):
                    continue

                domain, domain_specified, path, secure, expires, name, value = \
                    line.split("\t")
                secure = (secure == "TRUE")
                domain_specified = (domain_specified == "TRUE")
                if name == "":
                    # cookies.txt regards 'Set-Cookie: foo' as a cookie
                    # with no name, whereas http.cookiejar regards it as a
                    # cookie with no value.
                    name = value
                    value = None

                initial_dot = domain.startswith(".")
                assert domain_specified == initial_dot

                discard = False
                if expires in ("0", ""):
                    expires = None
                    discard = True

                # assume path_specified is false
                c = http.cookiejar.Cookie(
                    0, name, value,
                    None, False,
                    domain, domain_specified, initial_dot,
                    path, False,
                    secure,
                    expires,
                    discard,
                    None,
                    None,
                    {})
                if not ignore_discard and c.discard:
                    continue
                if not ignore_expires and c.is_expired(now):
                    continue
                self.set_cookie(c)

        except OSError:
            raise
        except Exception:
            f = io.StringIO()
            traceback.print_exc(None, f)
            msg = f.getvalue()
            warnings.warn("http.cookiejar bug!\n%s" % msg, stacklevel=2)
            raise http.cookiejar.LoadError(
                "invalid Netscape format cookies file %r: %r" %
                (filename, line))

    def save(self, filename=None, ignore_discard=False, ignore_expires=False):
        if filename is None:
            if self.filename is not None: filename = self.filename
            else: raise ValueError(http.cookiejar.MISSING_FILENAME_TEXT)

        with open(filename, "w") as f:
            f.write(self.header)
            now = time.time()
            for cookie in self:
                if not ignore_discard and cookie.discard:
                    continue
                if not ignore_expires and cookie.is_expired(now):
                    continue
                if cookie.secure:
                    secure = "TRUE"
                else:
                    secure = "FALSE"
                if cookie.domain.startswith("."):
                    initial_dot = "TRUE"
                else:
                    initial_dot = "FALSE"
                if cookie.expires is not None:
                    expires = str(cookie.expires)
                else:
                    expires = "0"
                if cookie.value is None:
                    # cookies.txt regards 'Set-Cookie: foo' as a cookie
                    # with no name, whereas http.cookiejar regards it as a
                    # cookie with no value.
                    name = ""
                    value = cookie.name
                else:
                    name = cookie.name
                    value = cookie.value
                f.write(
                    "\t".join([cookie.domain, initial_dot, cookie.path,
                               secure, expires, name, value]) +
                    "\n")
