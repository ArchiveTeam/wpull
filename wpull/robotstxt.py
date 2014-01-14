import robotexclusionrulesparser


class RobotsTxtPool(object):
    def __init__(self):
        self._parsers = {}

    def has_parser(self, request):
        key = self.url_info_key(request.url_info)
        return key in self._parsers

    def can_fetch(self, request):
        key = self.url_info_key(request.url_info)

        parser = self._parsers[key]
        return parser.is_allowed(request.fields.get('user-agent', ''),
            request.url_info.url)

    def load_robots_txt(self, url_info, text):
        key = self.url_info_key(url_info)
        parser = robotexclusionrulesparser.RobotExclusionRulesParser()
        parser.parse(text)

        self._parsers[key] = parser

    @classmethod
    def url_info_key(cls, url_info):
        return (url_info.scheme, url_info.hostname, url_info.port)
