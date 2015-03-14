'''Host filtering.'''


class HostFilter(object):
    '''Accept or reject hostnames.'''
    def __init__(self, accept_domains=None, reject_domains=None,
                 accept_hostnames=None, reject_hostnames=None):
        self._accept_domains = accept_domains
        self._reject_domains = reject_domains
        self._accept_hostnames = accept_hostnames
        self._reject_hostnames = reject_hostnames

    @classmethod
    def suffix_match(cls, domain_list, target_domain):
        for domain in domain_list:
            if target_domain.endswith(domain):
                return True

    def test(self, host):
        if self._accept_domains and not self.suffix_match(self._accept_domains, host):
            return False

        if self._accept_hostnames and host not in self._accept_hostnames:
            return False

        if self._reject_domains and self.suffix_match(self._reject_domains, host):
            return False

        if self._reject_hostnames and host in self._reject_hostnames:
            return False

        return True
