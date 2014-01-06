# encoding=utf-8
import time


try:
    from collections import Counter
except ImportError:
    from wpull.backport.collections import Counter


class Statistics(object):
    def __init__(self):
        self.start_time = None
        self.stop_time = None
        self.files = 0
        self.size = 0
        self.errors = Counter()

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.stop_time = time.time()

    @property
    def duration(self):
        return self.stop_time - self.start_time

    def increment(self, size):
        self.files += 1
        self.size += size
