'''Printing progress reports.'''
import contextlib
import datetime
import gettext
import http
import itertools
import re
import sys
import time

from wpull.bandwidth import BandwidthMeter
from wpull.recorder.base import BaseRecorder, BaseRecorderSession
import wpull.string


_ = gettext.gettext


class ProgressRecorder(BaseRecorder):
    '''Print file download progress as dots or a bar.

    Args:
        bar_style (bool): If True, print as a progress bar. If False,
            print dots every few seconds.
        stream: A file object. Default is usually stderr.
    '''
    def __init__(self, bar_style=False, stream=sys.stderr):
        self._bar_style = bar_style
        self._stream = stream

    @contextlib.contextmanager
    def session(self):
        if self._bar_style:
            yield BarProgressRecorderSession(stream=self._stream)
        else:
            yield DotProgressRecorderSession(stream=self._stream)


class BaseProgressRecorderSession(BaseRecorderSession):
    '''Base Progress Recorder Session.'''
    def __init__(self, stream=sys.stderr):
        self._stream = stream
        self._bytes_received = 0
        self._content_length = None
        self._response = None

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

    def pre_request(self, request):
        self._println()
        self._print(
            _('Fetch {url}... ').format(url=request.url_info.url),
        )
        self._flush()

    def pre_response(self, response):
        # FIXME: FTP and HTTP abstractions aren't working here
        if response.protocol == 'ftp':
            self._println()
            self._print(
            _('Fetch {url}... ').format(url=response.request.url_info.url),
            )

        self._println(response.response_code(),
                      wpull.string.printable_str(response.response_message()))

        if hasattr(response, 'fields'):
            content_length = response.fields.get('Content-Length')
            content_type = response.fields.get('Content-Type')
        elif hasattr(response, 'file_transfer_size'):
            content_length = response.file_transfer_size
            content_type = None
        else:
            content_length = None
            content_type = None

        if content_length:
            try:
                self._content_length = int(content_length)
            except ValueError:
                self._content_length = None

        self._println(
            _('  Length: {content_length} [{content_type}]').format(
                content_length=self._content_length or _('none'),
                content_type=wpull.string.printable_str(
                    content_type or _('none')
                )
            ),
        )

        self._response = response

    def response_data(self, data):
        if not self._response:
            return

        self._bytes_received += len(data)

    def response(self, response):
        self._println()
        self._println(
            _('  Bytes received: {bytes_received}').format(
                bytes_received=self._bytes_received)
        )
        self._println()


class DotProgressRecorderSession(BaseProgressRecorderSession):
    '''Dot Progress Recorder Session.

    This session is responsible for printing dots every few seconds
    when it receives data.
    '''
    def __init__(self, dot_interval=2.0, **kwargs):
        super().__init__(**kwargs)
        self._last_flush_time = 0
        self._dot_interval = dot_interval

    def response_data(self, data):
        super().response_data(data)

        if not self._response:
            return

        time_now = time.time()

        if time_now - self._last_flush_time > self._dot_interval:
            self._print_dots()
            self._flush()

            self._last_flush_time = time_now

    def _print_dots(self):
        '''Print a dot.'''
        self._print('.')


class BarProgressRecorderSession(BaseProgressRecorderSession):
    '''Bar Progress Recorder Session.

    This session is responsible for displaying the ASCII bar
    and stats.
    '''
    def __init__(self, update_interval=0.5, bar_width=25, **kwargs):
        super().__init__(**kwargs)
        self._last_flush_time = 0
        self._update_interval = update_interval
        self._bytes_continued = 0
        self._total_size = None
        self._bar_width = bar_width
        self._throbber_index = 0
        self._throbber_iter = itertools.cycle(
            itertools.chain(
                range(bar_width), reversed(range(1, bar_width - 1))
            ))
        self._bandwidth_meter = BandwidthMeter()
        self._start_time = time.time()

    def pre_response(self, response):
        super().pre_response(response)

        if response.protocol == 'http' and \
                response.status_code == http.client.PARTIAL_CONTENT:
            match = re.search(
                r'bytes +([0-9]+)-([0-9]+)/([0-9]+)',
                response.fields.get('Content-Range', '')
            )

            if match:
                self._bytes_continued = int(match.group(1))
                self._total_size = int(match.group(3))

        elif response.protocol == 'ftp' and response.restart_value:
            self._bytes_continued = response.restart_value
            self._total_size = self._content_length
        else:
            self._total_size = self._content_length

    def response_data(self, data):
        super().response_data(data)

        if not self._response:
            return

        self._bandwidth_meter.feed(len(data))

        time_now = time.time()

        if time_now - self._last_flush_time > self._update_interval:
            self._print_status()
            self._stream.flush()

            self._last_flush_time = time_now

    def response(self, response):
        self._print_status()
        self._stream.flush()
        super().response(response)

    def _print_status(self):
        '''Print an entire status line including bar and stats.'''
        self._clear_line()

        self._print('  ')

        if self._total_size:
            self._print_percent()
            self._print(' ')
            self._print_bar()
        else:
            self._print_throbber()

        self._print(' ')
        self._print_size_downloaded()
        self._print(' ')
        self._print_duration()
        self._print(' ')
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
            position_bytes = position_fraction * self._total_size

            if position_bytes < self._bytes_continued:
                self._print('+')
            elif (position_bytes <=
                  self._bytes_continued + self._bytes_received):
                self._print('=')
            else:
                self._print(' ')

        self._print(']')

    def _print_size_downloaded(self):
        '''Print the bytes downloaded.'''
        self._print(wpull.string.format_size(self._bytes_received))

    def _print_duration(self):
        '''Print the elapsed download time.'''
        duration = int(time.time() - self._start_time)
        self._print(datetime.timedelta(seconds=duration))

    def _print_speed(self):
        '''Print the current speed.'''
        if self._bandwidth_meter.num_samples:
            speed = self._bandwidth_meter.speed()
            speed_str = _('{preformatted_file_size}/s').format(
                preformatted_file_size=wpull.string.format_size(speed)
            )
        else:
            speed_str = _('-- B/s')

        self._print(speed_str)

    def _print_percent(self):
        '''Print how much is done in percentage.'''
        fraction_done = ((self._bytes_continued + self._bytes_received) /
                         self._total_size)

        self._print('{fraction_done:.1%}'.format(fraction_done=fraction_done))
