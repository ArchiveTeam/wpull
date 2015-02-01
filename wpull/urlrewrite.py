'''URL rewriting.'''
import re
from wpull.url import parse_url_or_log


class URLRewriter(object):
    def __init__(self, hash_fragment=False, session_id=False):
        self._hash_fragment_enabled = hash_fragment
        self._session_id_enabled = session_id

    def rewrite(self, url_info):
        if url_info.scheme not in ('http', 'https'):
            return url_info

        if self._session_id_enabled:
            url = '{scheme}://{authority}{path}?{query}#{fragment}'.format(
                scheme=url_info.scheme,
                authority=url_info.authority,
                path=strip_path_session_id(url_info.path),
                query=strip_query_session_id(url_info.query),
                fragment=url_info.fragment,
            )
            url_info = parse_url_or_log(url) or url_info

        if self._hash_fragment_enabled and url_info.fragment.startswith('!'):
            if url_info.query:
                url = '{}&_escaped_fragment_={}'.format(url_info.url,
                                                        url_info.fragment[1:])
            else:
                url = '{}?_escaped_fragment_={}'.format(url_info.url,
                                                        url_info.fragment[1:])

            url_info = parse_url_or_log(url) or url_info

        return url_info


# The strip session ID functions are based from the surt project.
# https://github.com/internetarchive/surt/blob/746f506dd6f0798adaa5bfd92101b73ed00f2831/surt/URLRegexTransformer.py
# Copyright 2012-2013 Internet Archive. AGPL v3.
SESSION_ID_PATH_PATTERNS = (
    re.compile("^(.*/)(\((?:[a-z]\([0-9a-z]{24}\))+\)/)([^\?]+\.aspx.*)$", re.I),
    re.compile("^(.*/)(\\([0-9a-z]{24}\\)/)([^\\?]+\\.aspx.*)$", re.I),
)

def strip_path_session_id(path):
    '''Strip session ID from URL path.'''
    for pattern in SESSION_ID_PATH_PATTERNS:
        match = pattern.match(path)
        if match:
            path = match.group(1) + match.group(3)

    return path


SESSION_ID_QUERY_PATTERNS = (
    re.compile("^(.*)(?:jsessionid=[0-9a-zA-Z]{32})(?:&(.*))?$", re.I),
    re.compile("^(.*)(?:phpsessid=[0-9a-zA-Z]{32})(?:&(.*))?$", re.I),
    re.compile("^(.*)(?:sid=[0-9a-zA-Z]{32})(?:&(.*))?$", re.I),
    re.compile("^(.*)(?:ASPSESSIONID[a-zA-Z]{8}=[a-zA-Z]{24})(?:&(.*))?$", re.I),
    re.compile("^(.*)(?:cfid=[^&]+&cftoken=[^&]+)(?:&(.*))?$", re.I),
)

def strip_query_session_id(query):
    for pattern in SESSION_ID_QUERY_PATTERNS:
        match = pattern.match(query)
        if match:
            if match.group(2):
                query = match.group(1) + match.group(2)
            else:
                query = match.group(1)

    return query
