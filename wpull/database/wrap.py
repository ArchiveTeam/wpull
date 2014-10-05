'''URL table wrappers.'''
from wpull.database.base import BaseURLTable
from wpull.hook import HookableMixin, HookDisconnected
from wpull.url import parse_url_or_log
from wpull.item import Status


class URLTableHookWrapper(BaseURLTable, HookableMixin):
    '''URL table wrapper with scripting hooks.

    Args:
        url_table: URL table.

    Attributes:
        url_table: URL table.
    '''

    def __init__(self, url_table):
        super().__init__()
        self.url_table = url_table
        self._queue_counter = 0

        self.register_hook('queued_url', 'dequeued_url')

    def queue_count(self):
        '''Return the number of URLs queued in this session.'''
        return self._queue_counter

    def count(self):
        return self.url_table.count()

    def get_one(self, url):
        return self.url_table.get_one(url)

    def get_all(self):
        return self.url_table.get_all()

    def add_many(self, urls, **kwargs):
        added_urls = tuple(self.url_table.add_many(urls, **kwargs))

        if self.is_hook_connected('queued_url'):
            for url in added_urls:
                url_info = parse_url_or_log(url)
                if url_info:
                    self._queue_counter += 1
                    self.call_hook('queued_url', url_info)

        return added_urls

    def check_out(self, *args, **kwargs):
        url_record = self.url_table.check_out(*args, **kwargs)
        self._queue_counter -= 1

        try:
            self.call_hook('dequeued_url', url_record.url_info, url_record)
        except HookDisconnected:
            pass

        return url_record

    def check_in(self, url, new_status, *args, **kwargs):
        if new_status == Status.error and self.is_hook_connected('queued_url'):
            self._queue_counter += 1
            url_info = parse_url_or_log(url)

            if url_info:
                self.call_hook('queued_url', url_info)

        return self.url_table.check_in(url, new_status, *args, **kwargs)

    def update_one(self, *args, **kwargs):
        return self.url_table.update_one(*args, **kwargs)

    def release(self):
        return self.url_table.release()

    def remove_many(self, urls):
        return self.url_table.remove_many(urls)

    def close(self):
        return self.url_table.close()

    def add_visits(self, visits):
        return self.url_table.add_visits(visits)

    def get_revisit_id(self, url, payload_digest):
        return self.url_table.get_revisit_id(url, payload_digest)
