# encoding=utf8
'''Redirection tracking.'''
import wpull.url


class RedirectTracker(object):
    '''Keeps track of HTTP document URL redirects.

    Args:
        max_redirects (int): The maximum number of redirects to allow.
        codes: The HTTP status codes indicating a redirect where the method
            can change to "GET".
        repeat_codes: The HTTP status codes indicating a redirect where
            the method cannot change and future requests should be repeated.
    '''
    REDIRECT_CODES = (301, 302, 303)
    REPEAT_REDIRECT_CODES = (307, 308)

    def __init__(self, max_redirects=20, codes=REDIRECT_CODES,
                 repeat_codes=REPEAT_REDIRECT_CODES):
        self._max_redirects = max_redirects
        self._codes = codes
        self._repeat_codes = repeat_codes
        self._response = None
        self._num_redirects = 0

    def load(self, response):
        '''Load the response and increment the counter.

        Args:
            response (:class:`.http.request.Response`): The response from
                a previous request.
        '''
        self._response = response

        if self.next_location(raw=True):
            self._num_redirects += 1

    def next_location(self, raw=False):
        '''Returns the next location.

        Args:
            raw (bool): If True, the original string contained in the Location
                field will be returned. Otherwise, the URL will be
                normalized to a complete URL.

        Returns:
            str, None: If str, the location. Otherwise, no next location.
        '''
        if self._response:
            location = self._response.fields.get('location')

            if not location or raw:
                return location

            return wpull.url.urljoin(self._response.request.url_info.url,
                                     location)

    def is_redirect(self):
        '''Return whether the response contains a redirect code.'''
        if self._response:
            status_code = self._response.status_code
            return status_code in self._codes \
                or status_code in self._repeat_codes

    def is_repeat(self):
        '''Return whether the next request should be repeated.'''
        if self._response:
            return self._response.status_code in self._repeat_codes

    def count(self):
        '''Return the number of redirects received so far.'''
        return self._num_redirects

    def exceeded(self):
        '''Return whether the number of redirects has exceeded the maximum.'''
        return self._num_redirects > self._max_redirects
