"""
A robot exclusion rules parser for Python by Philip Semanchuk

Full documentation, examples and a comparison to Python's robotparser module 
reside here:
http://NikitaTheSpider.com/python/rerp/

Comments, bug reports, etc. are most welcome via email to:
   philip@semanchuk.com

Simple usage examples:

    import robotexclusionrulesparser
    
    rerp = robotexclusionrulesparser.RobotExclusionRulesParser()

    try:
        rerp.fetch('http://www.example.com/robots.txt')
    except:
        # See the documentation for expected errors
        pass
    
    if rerp.is_allowed('CrunchyFrogBot', '/foo.html'):
        print "It is OK to fetch /foo.html"

OR supply the contents of robots.txt yourself:

    rerp = RobotExclusionRulesParser()
    s = open("robots.txt").read()
    rerp.parse(s)
    
    if rerp.is_allowed('CrunchyFrogBot', '/foo.html'):
        print "It is OK to fetch /foo.html"

The function is_expired() tells you if you need to fetch a fresh copy of 
this robots.txt.
    
    if rerp.is_expired():
        # Get a new copy
        pass


RobotExclusionRulesParser supports __unicode__() and __str()__ so you can print
an instance to see the its rules in robots.txt format.

The comments refer to MK1994, MK1996 and GYM2008. These are:
MK1994 = the 1994 robots.txt draft spec (http://www.robotstxt.org/orig.html)
MK1996 = the 1996 robots.txt draft spec (http://www.robotstxt.org/norobots-rfc.txt)
GYM2008 = the Google-Yahoo-Microsoft extensions announced in 2008
(http://www.google.com/support/webmasters/bin/answer.py?hl=en&answer=40360)


This code is released under the following BSD license --

Copyright (c) 2010, Philip Semanchuk
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
    * Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
    * Neither the name of robotexclusionrulesparser nor the
      names of its contributors may be used to endorse or promote products
      derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY ITS CONTRIBUTORS ''AS IS'' AND ANY
EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL Philip Semanchuk BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import sys
PY_MAJOR_VERSION = sys.version_info[0]

if PY_MAJOR_VERSION < 3:
    from urlparse import urlparse as urllib_urlparse
    from urlparse import urlunparse as urllib_urlunparse
    from urllib import unquote as urllib_unquote
    import urllib2 as urllib_request
    import urllib2 as urllib_error
else:
    import urllib.request as urllib_request
    import urllib.error as urllib_error
    from urllib.parse import unquote as urllib_unquote
    from urllib.parse import urlparse as urllib_urlparse
    from urllib.parse import urlunparse as urllib_urlunparse

import re
import time
import calendar
# rfc822 is deprecated since Python 2.3, but the functions I need from it
# are in email.utils which isn't present until Python 2.5. ???
try:
   import email.utils as email_utils
except ImportError:
   import rfc822 as email_utils


# These are the different robots.txt syntaxes that this module understands. 
# Hopefully this list will never have more than two elements.
MK1996 = 1
GYM2008 = 2

_end_of_line_regex = re.compile(r"(?:\r\n)|\r|\n")

# This regex is a little more generous than the spec because it accepts 
# "User-agent" or "Useragent" (without a dash). MK1994/96 permits only the 
# former. The regex also doesn't insist that "useragent" is at the exact 
# beginning of the line, which makes this code immune to confusion caused 
# by byte order markers. 
_directive_regex = re.compile("(allow|disallow|user[-]?agent|sitemap|crawl-delay):[ \t]*(.*)", re.IGNORECASE)

# This is the number of seconds in a week that I use to determine the default 
# expiration date defined in MK1996.
SEVEN_DAYS = 60 * 60 * 24 * 7

# This controls the max number of bytes read in as a robots.txt file. This 
# is just a bit of defensive programming in case someone accidentally sends 
# an ISO file in place of their robots.txt. (It happens...)  Suggested by 
# Dima Brodsky.
MAX_FILESIZE = 100 * 1024   # 100k 

# Control characters are everything < 0x20 and 0x7f. 
_control_characters_regex = re.compile(r"""[\000-\037]|\0177""")

# Charset extraction regex for pulling the encoding (charset) out of a 
# content-type header.
_charset_extraction_regex = re.compile(r"""charset=['"]?(?P<encoding>[^'"]*)['"]?""")


def _raise_error(error, message):
    # I have to exec() this code because the Python 2 syntax is invalid
    # under Python 3 and vice-versa.
    s = "raise "
    s += "error, message" if (PY_MAJOR_VERSION == 2) else "error(message)" 
        
    exec(s)


def _unquote_path(path):
    # MK1996 says, 'If a %xx encoded octet is encountered it is unencoded 
    # prior to comparison, unless it is the "/" character, which has 
    # special meaning in a path.'
    path = re.sub("%2[fF]", "\n", path)
    path = urllib_unquote(path)
    return path.replace("\n", "%2F")


def _scrub_data(s):
    # Data is either a path or user agent name; i.e. the data portion of a 
    # robots.txt line. Scrubbing it consists of (a) removing extraneous 
    # whitespace, (b) turning tabs into spaces (path and UA names should not 
    # contain tabs), and (c) stripping control characters which, like tabs, 
    # shouldn't be present. (See MK1996 section 3.3 "Formal Syntax".)
    s = _control_characters_regex.sub("", s)
    s = s.replace("\t", " ")
    return s.strip()
    
    
def _parse_content_type_header(header):
    media_type = ""
    encoding = ""

    # A typical content-type looks like this:    
    #    text/plain; charset=UTF-8
    # The portion after "text/plain" is optional and often not present.
    # ref: http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.7

    if header:
        header = header.strip().lower()
    else:
        header = ""
       
    chunks = [s.strip() for s in header.split(";")]
    media_type = chunks[0]
    if len(chunks) > 1:
        for parameter in chunks[1:]:
            m = _charset_extraction_regex.search(parameter)
            if m and m.group("encoding"):
                encoding = m.group("encoding")

    return media_type.strip(), encoding.strip()

    
class _Ruleset(object):
    """ _Ruleset represents a set of allow/disallow rules (and possibly a 
    crawl delay) that apply to a set of user agents.
    
    Users of this module don't need this class. It's available at the module
    level only because RobotExclusionRulesParser() instances can't be 
    pickled if _Ruleset isn't visible a the module level.    
    """
    ALLOW = 1
    DISALLOW = 2

    def __init__(self):
        self.robot_names = [ ]
        self.rules = [ ]
        self.crawl_delay = None

    def __str__(self):
        s = self.__unicode__()
        if PY_MAJOR_VERSION == 2:
            s = s.encode("utf-8")

        return s

    def __unicode__(self):
        d = { self.ALLOW : "Allow", self.DISALLOW : "Disallow" }

        s = ''.join( ["User-agent: %s\n" % name for name in self.robot_names] )

        if self.crawl_delay:
            s += "Crawl-delay: %s\n" % self.crawl_delay
    
        s += ''.join( ["%s: %s\n" % (d[rule_type], path) for rule_type, path in self.rules] )
    
        return s

    def add_robot_name(self, bot):
        self.robot_names.append(bot)
    
    def add_allow_rule(self, path):
        self.rules.append((self.ALLOW, _unquote_path(path)))
    
    def add_disallow_rule(self, path):
        self.rules.append((self.DISALLOW, _unquote_path(path)))
    
    def is_not_empty(self):
        return bool(len(self.rules)) and bool(len(self.robot_names))

    def is_default(self):
        return bool('*' in self.robot_names)

    def does_user_agent_match(self, user_agent):
        match = False
    
        for robot_name in self.robot_names:
            # MK1994 says, "A case insensitive substring match of the name 
            # without version information is recommended." MK1996 3.2.1 
            # states it even more strongly: "The robot must obey the first
            # record in /robots.txt that contains a User-Agent line whose 
            # value contains the name token of the robot as a substring. 
            # The name comparisons are case-insensitive."
            match = match or (robot_name == '*') or  \
                             (robot_name.lower() in user_agent.lower())
                
        return match

    def is_url_allowed(self, url, syntax=GYM2008):
        allowed = True
    
        # Schemes and host names are not part of the robots.txt protocol, 
        # so  I ignore them. It is the caller's responsibility to make 
        # sure they match.
        _, _, path, parameters, query, fragment = urllib_urlparse(url)
        url = urllib_urlunparse(("", "", path, parameters, query, fragment))

        url = _unquote_path(url)
    
        done = False
        i = 0
        while not done:
            rule_type, path = self.rules[i]

            if (syntax == GYM2008) and ("*" in path or path.endswith("$")):
                # GYM2008-specific syntax applies here
                # http://www.google.com/support/webmasters/bin/answer.py?hl=en&answer=40360
                if path.endswith("$"):
                    appendix = "$"
                    path = path[:-1]
                else:
                    appendix = ""
                parts = path.split("*")
                pattern = "%s%s" % \
                    (".*".join([re.escape(p) for p in parts]), appendix)
                if re.match(pattern, url):
                    # Ding!
                    done = True
                    allowed = (rule_type == self.ALLOW)
            else:  
                # Wildcards are either not present or are taken literally.
                if url.startswith(path):
                    # Ding!
                    done = True
                    allowed = (rule_type == self.ALLOW)
                    # A blank path means "nothing", so that effectively 
                    # negates the value above. 
                    # e.g. "Disallow:   " means allow everything
                    if not path:
                        allowed = not allowed


            i += 1
            if i == len(self.rules):
                done = True
            
        return allowed


class RobotExclusionRulesParser(object):
    """A parser for robots.txt files."""
    def __init__(self):
        self._source_url = ""
        self.user_agent = None
        self.use_local_time = True
        self.expiration_date = self._now() + SEVEN_DAYS
        self._response_code = 0
        self._sitemaps = [ ]
        self.__rulesets = [ ]
        

    @property
    def source_url(self): 
        """The URL from which this robots.txt was fetched. Read only."""
        return self._source_url

    @property
    def response_code(self): 
        """The remote server's response code. Read only."""
        return self._response_code

    @property
    def sitemap(self): 
        """Deprecated; use 'sitemaps' instead. Returns the sitemap URL present
        in the robots.txt, if any. Defaults to None. Read only. """
        _raise_error(DeprecationWarning, "The sitemap property is deprecated. Use 'sitemaps' instead.")

    @property
    def sitemaps(self): 
        """The sitemap URLs present in the robots.txt, if any. Defaults 
        to an empty list. Read only."""
        return self._sitemaps

    @property
    def is_expired(self):
        """True if the difference between now and the last call
        to fetch() exceeds the robots.txt expiration. 
        """
        return self.expiration_date <= self._now()     


    def _now(self):
        if self.use_local_time:
            return time.time()
        else:
            # What the heck is timegm() doing in the calendar module?!?
            return calendar.timegm(time.gmtime())


    def is_allowed(self, user_agent, url, syntax=GYM2008):
        """True if the user agent is permitted to visit the URL. The syntax 
        parameter can be GYM2008 (the default) or MK1996 for strict adherence 
        to the traditional standard.
        """        
        if PY_MAJOR_VERSION < 3:
            # The robot rules are stored internally as Unicode. The two lines 
            # below ensure that the parameters passed to this function are 
            # also Unicode. If those lines were not present and the caller 
            # passed a non-Unicode user agent or URL string to this function,
            # Python would silently convert it to Unicode before comparing it
            # to the robot rules. Such conversions use the default encoding 
            # (usually US-ASCII) and if the string couldn't be converted using
            # that encoding, Python would raise a UnicodeError later on in the
            # guts of this code which would be confusing. 
            # Converting the strings to Unicode here doesn't make the problem
            # go away but it does make the conversion explicit so that 
            # failures are easier to understand. 
            if not isinstance(user_agent, unicode):
                user_agent = user_agent.decode()
            if not isinstance(url, unicode):
                url = url.decode()
        
        if syntax not in (MK1996, GYM2008):
            _raise_error(ValueError, "Syntax must be MK1996 or GYM2008")
    
        for ruleset in self.__rulesets:
            if ruleset.does_user_agent_match(user_agent):
                return ruleset.is_url_allowed(url, syntax)
                
        return True


    def get_crawl_delay(self, user_agent):
        """Returns a float representing the crawl delay specified for this 
        user agent, or None if the crawl delay was unspecified or not a float.
        """
        # See is_allowed() comment about the explicit unicode conversion.
        if (PY_MAJOR_VERSION < 3) and (not isinstance(user_agent, unicode)):
            user_agent = user_agent.decode()
    
        for ruleset in self.__rulesets:
            if ruleset.does_user_agent_match(user_agent):
                return ruleset.crawl_delay
                
        return None


    def fetch(self, url, timeout=None):
        """Attempts to fetch the URL requested which should refer to a 
        robots.txt file, e.g. http://example.com/robots.txt.
        """

        # ISO-8859-1 is the default encoding for text files per the specs for
        # HTTP 1.0 (RFC 1945 sec 3.6.1) and HTTP 1.1 (RFC 2616 sec 3.7.1).
        # ref: http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.7.1
        encoding = "iso-8859-1"
        content = ""
        expires_header = None
        content_type_header = None
        self._response_code = 0
        self._source_url = url

        if self.user_agent:
            req = urllib_request.Request(url, None, 
                                         { 'User-Agent' : self.user_agent })
        else:
            req = urllib_request.Request(url)

        try:
            if timeout:
                f = urllib_request.urlopen(req, timeout=timeout)
            else:
                f = urllib_request.urlopen(req)

            content = f.read(MAX_FILESIZE)
            # As of Python 2.5, f.info() looks like it returns the HTTPMessage
            # object created during the connection. 
            expires_header = f.info().get("expires")
            content_type_header = f.info().get("Content-Type")
            # As of Python 2.4, this file-like object reports the response 
            # code, too. 
            if hasattr(f, "code"):
                self._response_code = f.code
            else:
                self._response_code = 200
            f.close()
        except urllib_error.URLError:
            # This is a slightly convoluted way to get the error instance,
            # but it works under Python 2 & 3. 
            error_instance = sys.exc_info()
            if len(error_instance) > 1:
                error_instance = error_instance[1]
            if hasattr(error_instance, "code"):
                self._response_code = error_instance.code
                
        # MK1996 section 3.4 says, "...robots should take note of Expires 
        # header set by the origin server. If no cache-control directives 
        # are present robots should default to an expiry of 7 days".
        
        # This code is lazy and looks at the Expires header but not 
        # Cache-Control directives.
        self.expiration_date = None
        if self._response_code >= 200 and self._response_code < 300:
            # All's well.
            if expires_header:
                self.expiration_date = email_utils.parsedate_tz(expires_header)
                
                if self.expiration_date:
                    # About time zones -- the call to parsedate_tz() returns a
                    # 10-tuple with the time zone offset in the 10th element. 
                    # There are 3 valid formats for HTTP dates, and one of 
                    # them doesn't contain time zone information. (UTC is 
                    # implied since all HTTP header dates are UTC.) When given
                    # a date that lacks time zone information, parsedate_tz() 
                    # returns None in the 10th element. mktime_tz() interprets
                    # None in the 10th (time zone) element to mean that the 
                    # date is *local* time, not UTC. 
                    # Therefore, if the HTTP timestamp lacks time zone info 
                    # and I run that timestamp through parsedate_tz() and pass
                    # it directly to mktime_tz(), I'll get back a local 
                    # timestamp which isn't what I want. To fix this, I simply
                    # convert a time zone of None to zero. It's much more 
                    # difficult to explain than to fix. =)
                    # ref: http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.3.1
                    if self.expiration_date[9] == None: 
                        self.expiration_date = self.expiration_date[:9] + (0,)
                
                    self.expiration_date = email_utils.mktime_tz(self.expiration_date)
                    if self.use_local_time: 
                        # I have to do a little more converting to get this 
                        # UTC timestamp into localtime.
                        self.expiration_date = time.mktime(time.gmtime(self.expiration_date)) 
                #else:
                    # The expires header was garbage.

        if not self.expiration_date: self.expiration_date = self._now() + SEVEN_DAYS

        if (self._response_code >= 200) and (self._response_code < 300):
            # All's well.
            media_type, encoding = _parse_content_type_header(content_type_header)
            # RFC 2616 sec 3.7.1 -- 
            # When no explicit charset parameter is provided by the sender, 
            # media subtypes  of the "text" type are defined to have a default
            # charset value of "ISO-8859-1" when received via HTTP.
            # http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.7.1
            if not encoding: 
                encoding = "iso-8859-1"
        elif self._response_code in (401, 403):
            # 401 or 403 ==> Go away or I will taunt you a second time! 
            # (according to MK1996)
            content = "User-agent: *\nDisallow: /\n"
        elif self._response_code == 404:
            # No robots.txt ==> everyone's welcome
            content = ""
        else:        
            # Uh-oh. I punt this up to the caller. 
            _raise_error(urllib_error.URLError, self._response_code)

        if ((PY_MAJOR_VERSION == 2) and isinstance(content, str)) or \
           ((PY_MAJOR_VERSION > 2)  and (not isinstance(content, str))):
            # This ain't Unicode yet! It needs to be.
            
            # Unicode decoding errors are another point of failure that I punt 
            # up to the caller.
            try:
                content = content.decode(encoding)
            except UnicodeError:
                _raise_error(UnicodeError,
                "Robots.txt contents are not in the encoding expected (%s)." % encoding)
            except (LookupError, ValueError):
                # LookupError ==> Python doesn't have a decoder for that encoding.
                # One can also get a ValueError here if the encoding starts with 
                # a dot (ASCII 0x2e). See Python bug 1446043 for details. This 
                # bug was supposedly fixed in Python 2.5.
                _raise_error(UnicodeError,
                        "I don't understand the encoding \"%s\"." % encoding)
        
        # Now that I've fetched the content and turned it into Unicode, I 
        # can parse it.
        self.parse(content)
        
        
    def parse(self, s):
        """Parses the passed string as a set of robots.txt rules."""
        self._sitemaps = [ ]
        self.__rulesets = [ ]
        
        if (PY_MAJOR_VERSION > 2) and (isinstance(s, bytes) or isinstance(s, bytearray)) or \
           (PY_MAJOR_VERSION == 2) and (not isinstance(s, unicode)):            
            s = s.decode("iso-8859-1")
    
        # Normalize newlines.
        s = _end_of_line_regex.sub("\n", s)
        
        lines = s.split("\n")
        
        previous_line_was_a_user_agent = False
        current_ruleset = None
        
        for line in lines:
            line = line.strip()
            
            if line and line[0] == '#':
                # "Lines containing only a comment are discarded completely, 
                # and therefore do not indicate a record boundary." (MK1994)
                pass
            else:
                # Remove comments
                i = line.find("#")
                if i != -1: line = line[:i]
        
                line = line.strip()
                
                if not line:
                    # An empty line indicates the end of a ruleset.
                    if current_ruleset and current_ruleset.is_not_empty():
                        self.__rulesets.append(current_ruleset)
                    
                    current_ruleset = None
                    previous_line_was_a_user_agent = False
                else:
                    # Each non-empty line falls into one of six categories:
                    # 1) User-agent: blah blah blah
                    # 2) Disallow: blah blah blah
                    # 3) Allow: blah blah blah
                    # 4) Crawl-delay: blah blah blah
                    # 5) Sitemap: blah blah blah
                    # 6) Everything else
                    # 1 - 5 are interesting and I find them with the regex 
                    # below. Category 6 I discard as directed by the MK1994 
                    # ("Unrecognised headers are ignored.")
                    # Note that 4 & 5 are specific to GYM2008 syntax, but 
                    # respecting them here is not a problem. They're just 
                    # additional information the the caller is free to ignore.
                    matches = _directive_regex.findall(line)
                    
                    # Categories 1 - 5 produce two matches, #6 produces none.
                    if matches:
                        field, data = matches[0]
                        field = field.lower()
                        data = _scrub_data(data)

                        # Matching "useragent" is a deviation from the 
                        # MK1994/96 which permits only "user-agent".
                        if field in ("useragent", "user-agent"):
                            if previous_line_was_a_user_agent:
                                # Add this UA to the current ruleset 
                                if current_ruleset and data:
                                    current_ruleset.add_robot_name(data)
                            else:
                                # Save the current ruleset and start a new one.
                                if current_ruleset and current_ruleset.is_not_empty():
                                    self.__rulesets.append(current_ruleset)
                                #else:
                                    # (is_not_empty() == False) ==> malformed 
                                    # robots.txt listed a UA line but provided
                                    # no name or didn't provide any rules 
                                    # for a named UA.
                                current_ruleset = _Ruleset()
                                if data: 
                                    current_ruleset.add_robot_name(data)
                            
                            previous_line_was_a_user_agent = True
                        elif field == "allow":
                            previous_line_was_a_user_agent = False
                            if current_ruleset:
                                current_ruleset.add_allow_rule(data)
                        elif field == "sitemap":
                            previous_line_was_a_user_agent = False
                            self._sitemaps.append(data)
                        elif field == "crawl-delay":
                            # Only Yahoo documents the syntax for Crawl-delay.
                            # ref: http://help.yahoo.com/l/us/yahoo/search/webcrawler/slurp-03.html
                            previous_line_was_a_user_agent = False
                            if current_ruleset:
                                try:
                                    current_ruleset.crawl_delay = float(data)
                                except ValueError:
                                    # Invalid crawl-delay -- ignore.
                                    pass
                        else:
                            # This is a disallow line
                            previous_line_was_a_user_agent = False
                            if current_ruleset:
                                current_ruleset.add_disallow_rule(data)

        if current_ruleset and current_ruleset.is_not_empty():
            self.__rulesets.append(current_ruleset)
            
        # Now that I have all the rulesets, I want to order them in a way 
        # that makes comparisons easier later. Specifically, any ruleset that 
        # contains the default user agent '*' should go at the end of the list
        # so that I only apply the default as a last resort. According to 
        # MK1994/96, there should only be one ruleset that specifies * as the 
        # user-agent, but you know how these things go.
        not_defaults = [r for r in self.__rulesets if not r.is_default()]
        defaults = [r for r in self.__rulesets if r.is_default()]

        self.__rulesets = not_defaults + defaults

    
    def __str__(self):
        s = self.__unicode__()
        if PY_MAJOR_VERSION == 2:
            s = s.encode("utf-8")

        return s

    def __unicode__(self):
        if self._sitemaps:
            s = "Sitemaps: %s\n\n" % self._sitemaps
        else: 
            s = ""
        if PY_MAJOR_VERSION < 3:
            s = unicode(s)
        # I also need to string-ify each ruleset. The function for doing so
        # varies under Python 2/3. 
        stringify = (unicode if (PY_MAJOR_VERSION == 2) else str)
        return s + '\n'.join( [stringify(ruleset) for ruleset in self.__rulesets] )


class RobotFileParserLookalike(RobotExclusionRulesParser):
    """A drop-in replacement for the Python standard library's RobotFileParser
    that retains all of the features of RobotExclusionRulesParser.
    """
    def __init__(self, url = ""):
        RobotExclusionRulesParser.__init__(self)
        
        self._user_provided_url = ""
        self.last_checked = None
        
        self.set_url(url)


    def set_url(self, url):
        # I don't want to stuff this into self._source_url because 
        # _source_url is set only as a side effect of calling fetch().
        self._user_provided_url = url
        
    
    def read(self):
        RobotExclusionRulesParser.fetch(self, self._user_provided_url)
        
    
    def parse(self, lines):
        RobotExclusionRulesParser.parse(self, ''.join(lines))


    def can_fetch(self, user_agent, url, syntax=GYM2008):
        return RobotExclusionRulesParser.is_allowed(self, user_agent, url, syntax)


    def mtime(self):
        return self.last_checked


    def modified(self):
        self.last_checked = time.time()
