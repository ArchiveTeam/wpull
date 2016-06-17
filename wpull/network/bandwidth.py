# encoding=utf-8
'''Network bandwidth.'''
import collections
import time


class BandwidthMeter(object):
    '''Calculates the speed of data transfer.

    Args:
        sample_size (int): The number of samples for measuring the speed.
        sample_min_time (float): The minimum duration between samples in
            seconds.
        stall_time (float): The time in seconds to consider no traffic
            to be connection stalled.
    '''
    def __init__(self, sample_size=20, sample_min_time=0.15, stall_time=5.0):
        self._bytes_transferred = 0
        self._samples = collections.deque(maxlen=sample_size)
        self._last_feed_time = time.time()
        self._sample_min_time = sample_min_time
        self._stall_time = stall_time
        self._stalled = False
        self._collected_bytes_transferred = 0

    @property
    def bytes_transferred(self):
        '''Return the number of bytes transferred

        Returns:
            int
        '''
        return self._bytes_transferred

    @property
    def stalled(self):
        '''Return whether the connection is stalled.

        Returns:
            bool
        '''
        return self._stalled

    @property
    def num_samples(self):
        '''Return the number of samples collected.'''
        return len(self._samples)

    def feed(self, data_len, feed_time=None):
        '''Update the bandwidth meter.

        Args:
            data_len (int): The number of bytes transfered since the last
                call to :func:`feed`.
            feed_time (float): Current time.
        '''
        self._bytes_transferred += data_len
        self._collected_bytes_transferred += data_len

        time_now = feed_time or time.time()
        time_diff = time_now - self._last_feed_time

        if time_diff < self._sample_min_time:
            return

        self._last_feed_time = time.time()

        if data_len == 0 and time_diff >= self._stall_time:
            self._stalled = True
            return

        self._samples.append((time_diff, self._collected_bytes_transferred))
        self._collected_bytes_transferred = 0

    def speed(self):
        '''Return the current transfer speed.

        Returns:
            int: The speed in bytes per second.
        '''
        if self._stalled:
            return 0

        time_sum = 0
        data_len_sum = 0

        for time_diff, data_len in self._samples:
            time_sum += time_diff
            data_len_sum += data_len

        if time_sum:
            return data_len_sum / time_sum
        else:
            return 0


class BandwidthLimiter(BandwidthMeter):
    '''Bandwidth rate limit calculator.'''
    def __init__(self, rate_limit):
        super().__init__(sample_min_time=0)
        self._rate_limit = rate_limit

    def sleep_time(self):
        if not self._samples or not self._rate_limit:
            return 0

        elapsed_time = 0
        byte_sum = 0

        for time_diff, data_len in self._samples:
            elapsed_time += time_diff
            byte_sum += data_len

        expected_elapsed_time = byte_sum / self._rate_limit

        if expected_elapsed_time > elapsed_time:
            sleep_time = expected_elapsed_time - elapsed_time
            if sleep_time < 0.001:
                return 0
            else:
                return sleep_time
        else:
            return 0
