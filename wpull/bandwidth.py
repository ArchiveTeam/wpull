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
        self._bytes_transfered = 0
        self._samples = collections.deque(maxlen=sample_size)
        self._last_feed_time = time.time()
        self._sample_min_time = sample_min_time
        self._stall_time = stall_time
        self._stalled = False
        self._collected_bytes_transfered = 0

    @property
    def bytes_transfered(self):
        '''Return the number of bytes tranfered

        Returns:
            int
        '''
        return self._bytes_transfered

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

    def feed(self, data_len):
        '''Update the bandwidth meter.

        Args:
            data_len (int): The number of bytes transfered since the last
                call to :func:`feed`.
        '''
        self._bytes_transfered += data_len
        self._collected_bytes_transfered += data_len

        time_now = time.time()
        time_diff = time_now - self._last_feed_time

        if time_diff < self._sample_min_time:
            return

        self._last_feed_time = time.time()

        if data_len == 0 and time_diff >= self._stall_time:
            self._stalled = True
            return

        self._samples.append((time_diff, self._collected_bytes_transfered))
        self._collected_bytes_transfered = 0

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
