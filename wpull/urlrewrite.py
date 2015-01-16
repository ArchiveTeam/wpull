'''URL rewriting.'''
from wpull.url import parse_url_or_log


class URLRewriter(object):
    def __init__(self):
        pass

    def rewrite(self, url_info):
        if url_info.fragment.startswith('!'):
            if url_info.query:
                url = '{}&_escaped_fragment_={}'.format(url_info.url,
                                                        url_info.fragment[1:])
            else:
                url = '{}?_escaped_fragment_={}'.format(url_info.url,
                                                        url_info.fragment[1:])

            return parse_url_or_log(url) or url_info
        else:
            return url_info
