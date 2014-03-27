# encoding=utf-8
'''Statistics.'''
import time

from wpull.network import BandwidthMeter


try:
    from collections import Counter
except ImportError:
    from wpull.backport.collections import Counter


class Statistics(object):
    '''Statistics.

    Attributes:
        start_time (float): Timestamp when the engine started.
        stop_time (float): Timestamp when the engine stopped.
        files (int): Number of files downloaded.
        size (int): Size of files in bytes.
        errors: a Counter mapping error types to integer.
        quota (int): Threshold of number of bytes when the download quota is
            exceeded.
        required_url_infos (set): A set of :class:`.url.URLInfo` that must
            be completed before the quota can be exceeded.
        bandwidth_meter (:class:`.network.BandwidthMeter`): The bandwidth
            meter.
    '''
    def __init__(self):
        self.start_time = None
        self.stop_time = None
        self.files = 0
        self.size = 0
        self.errors = Counter()
        self.quota = None
        self.required_url_infos = set()
        self.bandwidth_meter = BandwidthMeter()

    def start(self):
        '''Record the start time.'''
        self.start_time = time.time()
        self.bandwidth_meter.feed(1)

    def stop(self):
        '''Record the stop time.'''
        self.stop_time = time.time()

    @property
    def duration(self):
        '''Return the time in seconds the interval.'''
        return self.stop_time - self.start_time

    def increment(self, size):
        '''Increment the number of files downloaded.

        Args:
            size: The size of the file
        '''
        self.files += 1
        self.size += size
        self.bandwidth_meter.feed(size)

    @property
    def is_quota_exceeded(self):
        '''Return whether the quota is exceeded.'''
        if self.required_url_infos:
            return False

        if self.quota:
            return self.size >= self.quota

    def mark_done(self, url_info):
        '''Set the URLInfo as completed.'''
        if url_info in self.required_url_infos:
            self.required_url_infos.remove(url_info)
