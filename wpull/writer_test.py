# encoding=utf-8
import hashlib
import io
import os.path
import unittest

import wpull.testing.async
from wpull.path import PathNamer
from wpull.testing.ftp import FTPTestCase
from wpull.testing.goodapp import GoodAppTestCase
from wpull.testing.util import TempDirMixin
from wpull.writer import NullWriter, AntiClobberFileWriter, OverwriteFileWriter, \
    TimestampingFileWriter, SingleDocumentWriter
from wpull.protocol.http.request import Response as HTTPResponse
from wpull.protocol.http.request import Request as HTTPRequest
from wpull.protocol.ftp.request import Response as FTPResponse


class TestWriter(unittest.TestCase, TempDirMixin):
    def setUp(self):
        super().setUp()
        self.set_up_temp_dir()

    def tearDown(self):
        super().tearDown()
        self.tear_down_temp_dir()

    def test_null_writer(self):
        writer = NullWriter()
        session = writer.session()

        session.process_request(HTTPRequest())
        session.process_response(HTTPResponse())
        session.discard_document(HTTPResponse())
        session.save_document(HTTPResponse())
        self.assertIsNone(session.extra_resource_path('blah'))

    def get_path_namer(self):
        return PathNamer(os.getcwd(), use_dir=True)

    def test_new_file_and_clobber(self):
        writer = AntiClobberFileWriter(self.get_path_namer())
        session = writer.session()

        request1 = HTTPRequest('http://example.com/my_file.txt')
        response1 = HTTPResponse(status_code=200, reason='OK', request=request1)

        session.process_request(request1)
        session.process_response(response1)
        session.save_document(response1)

        self.assertTrue(os.path.exists('my_file.txt'))

        session = writer.session()

        request2 = HTTPRequest('http://example.com/my_file.txt')
        response2 = HTTPResponse(status_code=200, reason='OK', request=request2)

        session.process_request(request2)
        session.process_response(response2)
        session.save_document(response2)

        self.assertTrue(os.path.exists('my_file.txt'))

    def test_file_continue(self):
        writer = OverwriteFileWriter(self.get_path_namer(), file_continuing=True)
        session = writer.session()

        with open('my_file.txt', 'wb') as file:
            file.write(b'TEST')

        request = HTTPRequest('http://example.com/my_file.txt')
        session.process_request(request)

        self.assertIn('Range', request.fields)

        response = HTTPResponse(status_code=206, reason='Partial content', request=request)
        session.process_response(response)

        response.body.write(b'END')
        response.body.flush()

        session.save_document(response)

        with open('my_file.txt', 'rb') as file:
            data = file.read()

        self.assertEqual(b'TESTEND', data)

    def test_timestamping(self):
        writer = TimestampingFileWriter(self.get_path_namer())
        session = writer.session()

        local_timestamp = 634521600

        with open('my_file.txt', 'wb') as file:
            file.write(b'')

        os.utime('my_file.txt', (local_timestamp, local_timestamp))

        request = HTTPRequest('http://example.com/my_file.txt')
        session.process_request(request)

        self.assertIn('If-Modified-Since', request.fields)

        response = HTTPResponse(status_code=304, reason='Not modified', request=request)
        session.process_response(response)

    def test_dir_or_file_dir_got_first(self):
        writer = OverwriteFileWriter(self.get_path_namer())
        session = writer.session()

        os.mkdir('dir_or_file')

        request = HTTPRequest('http://example.com/dir_or_file')
        response = HTTPResponse(status_code=200, reason='OK', request=request)

        session.process_request(request)
        session.process_response(response)
        session.save_document(response)

        print(list(os.walk('.')))
        self.assertTrue(os.path.isdir('dir_or_file'))
        self.assertTrue(os.path.isfile('dir_or_file.f'))

    def test_dir_or_file_file_got_first(self):
        writer = OverwriteFileWriter(self.get_path_namer())
        session = writer.session()

        with open('dir_or_file', 'wb'):
            pass

        request = HTTPRequest('http://example.com/dir_or_file/')
        response = HTTPResponse(status_code=200, reason='OK', request=request)

        session.process_request(request)
        session.process_response(response)
        session.save_document(response)

        print(list(os.walk('.')))
        self.assertTrue(os.path.isdir('dir_or_file.d'))
        self.assertTrue(os.path.isfile('dir_or_file.d/index.html'))
        self.assertTrue(os.path.isfile('dir_or_file'))

    def test_adjust_extension(self):
        writer = AntiClobberFileWriter(self.get_path_namer(), adjust_extension=True)

        test_data = [
            ('text/html', '/mordor', 'mordor.html'),
            ('text/html', '/mordor?ring.asp', 'mordor?ring.asp.html'),
            ('text/html', '/mordor?ring.htm', 'mordor?ring.htm'),
            ('text/plain', '/static/my_file.txt', 'static/my_file.txt'),
            ('text/css', '/static/style.css', 'static/style.css'),
            ('text/css', '/static/style.css?hamster.exe', 'static/style.css?hamster.exe.css'),
            ('text/html', '/static/mojibake.html', 'static/mojibake.html'),
            ('text/html', '/static/mojibake.html?dolphin.png', 'static/mojibake.html?dolphin.png.html'),
        ]

        for mime_type, path, filename in test_data:
            session = writer.session()

            request = HTTPRequest('http://example.com' + path)
            response = HTTPResponse(status_code=200, reason='OK', request=request)
            response.fields['Content-Type'] = mime_type

            session.process_request(request)
            session.process_response(response)
            session.save_document(response)

            print(filename, list(os.walk('.')))
            self.assertTrue(os.path.exists(filename))

    def test_content_disposition(self):
        writer = AntiClobberFileWriter(self.get_path_namer(), content_disposition=True)

        test_data = [
            ('hello1.txt', 'hello1.txt'),
            ('hello2.txt;', 'hello2.txt'),
            ('"hello3.txt"', 'hello3.txt'),
            ('\'hello4.txt\'', 'hello4.txt'),

        ]

        for raw_filename, filename in test_data:
            session = writer.session()

            request = HTTPRequest('http://example.com')
            response = HTTPResponse(status_code=200, reason='OK', request=request)
            response.fields['Content-Disposition'] = 'attachment; filename={}'.format(raw_filename)

            session.process_request(request)
            session.process_response(response)
            session.save_document(response)

            print(list(os.walk('.')))
            self.assertTrue(os.path.exists(filename))

    def test_trust_server_names(self):
        writer = AntiClobberFileWriter(self.get_path_namer(), trust_server_names=True)
        session = writer.session()

        request1 = HTTPRequest('http://example.com')
        response1 = HTTPResponse(status_code=302, reason='Moved', request=request1)

        session.process_request(request1)
        session.process_response(response1)

        request2 = HTTPRequest('http://example.com/my_file.html')
        response2 = HTTPResponse(status_code=200, reason='OK', request=request2)

        session.process_request(request2)
        session.process_response(response2)

        session.save_document(response2)

        print(list(os.walk('.')))
        self.assertTrue(os.path.exists('my_file.html'))

    def test_single_document_writer(self):
        stream = io.BytesIO()

        writer = SingleDocumentWriter(stream, headers_included=True)
        session = writer.session()

        request1 = HTTPRequest('http://example.com/my_file1.txt')
        response1 = HTTPResponse(status_code=200, reason='OK', request=request1)

        session.process_request(request1)
        session.process_response(response1)

        response1.body.write(b'The content')

        session.save_document(response1)

        session = writer.session()

        request2 = HTTPRequest('http://example.com/my_file2.txt')
        response2 = HTTPResponse(status_code=200, reason='OK', request=request2)

        session.process_request(request2)
        session.process_response(response2)

        response1.body.write(b'Another thing')

        session.save_document(response2)

        data = stream.getvalue()

        self.assertIn(b'HTTP', data)
        self.assertIn(b'The content', data)
        self.assertIn(b'Another thing', data)
