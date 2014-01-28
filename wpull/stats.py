# encoding=utf-8
'''Statistics.'''
import time


try:
    from collections import Counter
except ImportError:
    from wpull.backport.collections import Counter


class Statistics(object):
    '''Statistics.

    Attributes:
        start_time: Timestamp when the engine started
        stop_time: Timestamp when the engine stopped
        files: Number of files downloaded
        size: Size of files in bytes
        errors: a Counter mapping error types to integer
    '''
    def __init__(self):
        self.start_time = None
        self.stop_time = None
        self.files = 0
        self.size = 0
        self.errors = Counter()

    def start(self):
        '''Record the start time.'''
        self.start_time = time.time()

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
