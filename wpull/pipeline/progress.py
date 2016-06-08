import datetime
import enum
import gettext
import logging
import sys
import time
import itertools
from typing import IO, cast
import http.client
import re

from wpull.application.hook import HookableMixin
from wpull.network.bandwidth import BandwidthMeter
import wpull.string
from wpull.protocol.abstract.request import BaseRequest, BaseResponse
from wpull.protocol.http.request import Response as HTTPResponse
from wpull.protocol.ftp.request import Response as FTPResponse

_ = gettext.gettext


class Measurement(enum.Enum):
    integer = 'integer'
    bytes = 'bytes'


class Progress(HookableMixin):
    '''Print file download progress as dots or a bar.

    Args:
        bar_style (bool): If True, print as a progress bar. If False,
            print dots every few seconds.
        stream: A file object. Default is usually stderr.
        human_format (true): If True, format sizes in units. Otherwise, output
            bits only.
    '''

    def __init__(self, stream: IO[str]=sys.stderr):
        super().__init__()

        self._stream = stream

        self.min_value = 0
        self.max_value = None
        self.current_value = 0
        self.continue_value = None
        self.measurement = Measurement.integer

        self.event_dispatcher.register('update')

    def update(self):
        self.event_dispatcher.notify('update', self)

    def reset(self):
        self.min_value = 0
        self.max_value = None
        self.current_value = 0
        self.continue_value = None
        self.measurement = Measurement.integer


class ProtocolProgress(Progress):
    class State(enum.Enum):
        idle = 'idle'
        sending_request = 'sending_request'
        sending_body = 'sending_body'
        receiving_response = 'receiving_response'
        receiving_body = 'receiving_body'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._state = self.State.sending_request

    def update_from_begin_request(self, request: BaseRequest):
        self._state = self.State.sending_request

        self.reset()
        self.measurement = Measurement.bytes

    def update_from_begin_response(self, response: BaseResponse):
        self._state = self.State.receiving_body

        self._process_response_sizes(response)

    def update_from_end_response(self, response: BaseResponse):
        self._state = self.State.idle

    def _process_response_sizes(self, response: BaseResponse):
        if hasattr(response, 'fields'):
            content_length = response.fields.get('Content-Length')
        elif hasattr(response, 'file_transfer_size'):
            content_length = response.file_transfer_size
        else:
            content_length = None

        if content_length:
            try:
                self.max_value = int(content_length)
            except ValueError:
                pass

        if response.protocol == 'http':
            response = cast(HTTPResponse, response)
            if not response.status_code == http.client.PARTIAL_CONTENT:
                return

            match = re.search(
                r'bytes +([0-9]+)-([0-9]+)/([0-9]+)',
                response.fields.get('Content-Range', '')
            )

            if match:
                self.continue_value = int(match.group(1))
                self.max_value = int(match.group(3))

        elif response.protocol == 'ftp':
            response = cast(FTPResponse, response)

            if response.restart_value:
                self.continue_value = response.restart_value

    def update_with_data(self, data):
        if self._state == self.State.receiving_body:
            self.current_value += len(data)
            self.update()


class ProgressPrinter(ProtocolProgress):
    def _print(self, *args):
        '''Convenience function for the print function.

        This function prints no newline.
        '''
        string = ' '.join([str(arg) for arg in args])
        print(string, end='', file=self._stream)

    def _println(self, *args):
        '''Convenience function for the print function.'''
        string = ' '.join([str(arg) for arg in args])
        print(string, file=self._stream)

    def _flush(self):
        '''Flush the print stream.'''
        self._stream.flush()

    def update_from_end_response(self, response: BaseResponse):
        super().update_from_end_response(response)

        self._println()


class DotProgress(ProgressPrinter):
    def __init__(self, *args, draw_interval: float=2.0, **kwargs):
        super().__init__(*args, **kwargs)

        self._draw_interval = draw_interval
        self._last_draw_time = 0

    def update(self):
        super().update()

        if self._state != self.State.receiving_body:
            return

        time_now = time.time()

        if time_now - self._last_draw_time > self._draw_interval:
            self._print_dots()
            self._flush()

            self._last_draw_time = time_now

    def _print_dots(self):
        '''Print a dot.'''
        self._print('.')


class BarProgress(ProgressPrinter):
    def __init__(self, *args, draw_interval: float=0.5, bar_width: int=25,
                 human_format: bool=True, **kwargs):
        super().__init__(*args, **kwargs)

        self._draw_interval = draw_interval
        self._bar_width = bar_width
        self._human_format = human_format

        self._throbber_index = 0
        self._throbber_iter = itertools.cycle(
            itertools.chain(
                range(bar_width), reversed(range(1, bar_width - 1))
            ))
        self._bandwidth_meter = BandwidthMeter()
        self._previous_value = 0
        self._last_draw_time = 0
        self._start_time = time.time()

    def update(self):
        super().update()

        if self._state != self.State.receiving_body:
            return

        difference = self.current_value - self._previous_value
        self._previous_value = self.current_value

        self._bandwidth_meter.feed(difference)

        time_now = time.time()

        if time_now - self._last_draw_time > self._draw_interval or self.current_value == self.max_value:
            self._print_status()
            self._flush()

            self._last_draw_time = time_now

    def _print_status(self):
        '''Print an entire status line including bar and stats.'''
        self._clear_line()

        self._print('  ')

        if self.max_value:
            self._print_percent()
            self._print(' ')
            self._print_bar()
        else:
            self._print_throbber()

        self._print(' ')

        if self.measurement == Measurement.bytes:
            self._print_size_downloaded()
        else:
            self._print(self.current_value)

        self._print(' ')
        self._print_duration()
        self._print(' ')

        if self.measurement == Measurement.bytes:
            self._print_speed()

        self._flush()

    def _clear_line(self):
        '''Print ANSI code to clear the current line.'''
        self._print('\x1b[1G')
        self._print('\x1b[2K')

    def _print_throbber(self):
        '''Print an indefinite progress bar.'''
        self._print('[')

        for position in range(self._bar_width):
            self._print('O' if position == self._throbber_index else ' ')

        self._print(']')

        self._throbber_index = next(self._throbber_iter)

    def _print_bar(self):
        '''Print a progress bar.'''
        self._print('[')

        for position in range(self._bar_width):
            position_fraction = position / (self._bar_width - 1)
            position_bytes = position_fraction * self.max_value

            if position_bytes < (self.continue_value or 0):
                self._print('+')
            elif position_bytes <= (self.continue_value or 0) + self.current_value:
                self._print('=')
            else:
                self._print(' ')

        self._print(']')

    def _print_size_downloaded(self):
        '''Print the bytes downloaded.'''
        self._print(wpull.string.format_size(self.current_value))

    def _print_duration(self):
        '''Print the elapsed download time.'''
        duration = int(time.time() - self._start_time)
        self._print(datetime.timedelta(seconds=duration))

    def _print_speed(self):
        '''Print the current speed.'''
        if self._bandwidth_meter.num_samples:
            speed = self._bandwidth_meter.speed()

            if self._human_format:
                file_size_str = wpull.string.format_size(speed)
            else:
                file_size_str = '{:.1f} b'.format(speed * 8)

            speed_str = _('{preformatted_file_size}/s').format(
                preformatted_file_size=file_size_str
            )
        else:
            speed_str = _('-- B/s')

        self._print(speed_str)

    def _print_percent(self):
        '''Print how much is done in percentage.'''
        fraction_done = ((self.continue_value or 0 + self.current_value) /
                         self.max_value)

        self._print('{fraction_done:.1%}'.format(fraction_done=fraction_done))
