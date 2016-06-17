# encoding=utf-8
'''Robots.txt exclusion directives.'''
import gettext
import logging

from wpull.thirdparty import robotexclusionrulesparser
from wpull.url import URLInfo

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class RobotsTxtPool(object):
    '''Pool of robots.txt parsers.'''
    def __init__(self):
        self._parsers = {}

    def has_parser(self, url_info: URLInfo):
        '''Return whether a parser has been created for the URL.'''
        key = self.url_info_key(url_info)
        return key in self._parsers

    def can_fetch(self, url_info: URLInfo, user_agent: str):
        '''Return whether the URL can be fetched.'''
        key = self.url_info_key(url_info)

        parser = self._parsers[key]
        return parser.is_allowed(user_agent, url_info.url)

    def load_robots_txt(self, url_info: URLInfo, text: str):
        '''Load the robot.txt file.'''
        key = self.url_info_key(url_info)
        parser = robotexclusionrulesparser.RobotExclusionRulesParser()
        parser.parse(text)

        self._parsers[key] = parser

    @classmethod
    def url_info_key(cls, url_info: URLInfo) -> tuple:
        return url_info.scheme, url_info.hostname, url_info.port
