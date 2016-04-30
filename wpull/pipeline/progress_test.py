import unittest

import sys

from wpull.pipeline.progress import DotProgress, BarProgress, Measurement, \
    ProgressPrinter
from wpull.protocol.http.request import Request as HTTPRequest
from wpull.protocol.http.request import Response as HTTPResponse
from wpull.protocol.ftp.request import Request as FTPRequest
from wpull.protocol.ftp.request import Response as FTPResponse
from wpull.protocol.ftp.request import Reply as FTPReply


class TestProgress(unittest.TestCase):
    def test_progress_dot(self):
        progress = DotProgress(stream=sys.stdout, draw_interval=0)

        progress.max_value = 100
        progress.min_value = 0

        progress.update()

        for dummy in range(100):
            progress.current_value += 1
            progress.update()

    def test_progress_bar_integer(self):
        progress = BarProgress(stream=sys.stdout, draw_interval=0)

        progress.max_value = 100
        progress.min_value = 0
        progress.current_value = 10

        progress.update()

        for dummy in range(100):
            progress.current_value += 1
            progress.update()

    def test_progress_bar_bytes(self):
        progress = BarProgress(stream=sys.stdout, draw_interval=0)

        progress.max_value = 100
        progress.min_value = 0
        progress.current_value = 10
        progress.measurement = Measurement.bytes

        progress.update()

        for dummy in range(100):
            progress.current_value += 1
            progress.update()

    def test_progress_http(self):
        progress = ProgressPrinter(stream=sys.stdout)

        request = HTTPRequest('http://example.com')
        response = HTTPResponse(206, 'OK')
        response.fields['Content-Size'] = '1024'
        response.fields['Content-Range'] = 'bytes 10-/2048'

        progress.update_from_begin_request(request)
        progress.update_from_begin_response(response)

        for dummy in range(100):
            progress.update_with_data(b'abc')

        progress.update_from_end_response(response)

    def test_progress_ftp(self):
        progress = ProgressPrinter(stream=sys.stdout)

        request = FTPRequest('ftp://example.com/example.txt')
        response = FTPResponse()
        response.reply = FTPReply(226, 'Closing data connection')
        response.file_transfer_size = 2048
        response.restart_value = 10

        progress.update_from_begin_request(request)
        progress.update_from_begin_response(response)

        for dummy in range(100):
            progress.update_with_data(b'abc')

        progress.update_from_end_response(response)
