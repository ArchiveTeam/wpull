# encoding=utf-8
'''Statistics.'''
import logging
import os
import shelve
import tempfile
import time
from collections import Counter
from typing import Optional

from wpull.database.base import BaseURLTable
from wpull.errors import ERROR_PRIORITIES
from wpull.network.bandwidth import BandwidthMeter

_logger = logging.getLogger(__name__)


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
        bandwidth_meter (:class:`.network.BandwidthMeter`): The bandwidth
            meter.
    '''
    def __init__(self, url_table: Optional[BaseURLTable]=None):
        self.start_time = None
        self.stop_time = None
        self.files = 0
        self.size = 0
        self.errors = Counter()
        self.quota = None
        self.bandwidth_meter = BandwidthMeter()
        self._url_table = url_table

    def start(self):
        '''Record the start time.'''
        self.start_time = time.time()
        self.bandwidth_meter.feed(1)

    def stop(self):
        '''Record the stop time.'''
        self.stop_time = time.time()

    @property
    def duration(self) -> float:
        '''Return the time in seconds the interval.'''
        return self.stop_time - self.start_time

    def increment(self, size: int):
        '''Increment the number of files downloaded.

        Args:
            size: The size of the file
        '''
        assert size >= 0, size

        self.files += 1
        self.size += size
        self.bandwidth_meter.feed(size)

    @property
    def is_quota_exceeded(self) -> bool:
        '''Return whether the quota is exceeded.'''

        if self.quota and self._url_table is not None:
            return self.size >= self.quota and \
                   self._url_table.get_root_url_todo_count() == 0

    def increment_error(self, error: Exception):
        '''Increment the error counter preferring base exceptions.'''
        _logger.debug('Increment error %s', error)

        for error_class in ERROR_PRIORITIES:
            if isinstance(error, error_class):
                self.errors[error_class] += 1
                return

        self.errors[type(error)] += 1
