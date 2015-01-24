
class ProxyCoprocessor(object):
    '''Proxy coprocessor.'''
    def __init__(self, proxy_server, cookie_jar=None):
        self._proxy_server = proxy_server
        self._cookie_jar = cookie_jar

        if cookie_jar:
            def request_callback(request):
                cookie_jar.add_cookie_header(request)

            def response_callback(request, response):
                cookie_jar.extract_cookies(response, request)

            proxy_server.request_callback = request_callback
            proxy_server.response_callback = response_callback
