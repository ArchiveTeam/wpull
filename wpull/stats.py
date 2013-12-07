import time
import collections


class Statistics(object):
    def __init__(self):
        self.start_time = None
        self.stop_time = None
        self.files = 0
        self.size = 0
        self.errors = collections.Counter()

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.stop_time = time.time()

    @property
    def duration(self):
        return self.stop_time - self.start_time
