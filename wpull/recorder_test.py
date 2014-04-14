# encoding=utf-8
import logging
import os.path

from wpull.backport.testing import unittest
from wpull.http.request import Request, Response
from wpull.recorder import WARCRecorder, WARCRecorderParams
import wpull.util
import wpull.version
from wpull.warc import WARCRecord
from wpull.database import URLTable


try:
    from tempfile import TemporaryDirectory
except ImportError:
    from wpull.backport.tempfile import TemporaryDirectory


_logger = logging.getLogger(__name__)


class RecorderTest(unittest.TestCase):
    def setUp(self):
        unittest.TestCase.setUp(self)
        self.original_dir = os.getcwd()
        self.temp_dir = TemporaryDirectory()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()
        os.chdir(self.original_dir)
        unittest.TestCase.tearDown(self)

    def test_warc_recorder(self):
        file_prefix = 'asdf'
        warc_filename = 'asdf.warc'
        cdx_filename = 'asdf.cdx'

        warc_recorder = WARCRecorder(
            file_prefix,
            params=WARCRecorderParams(
                compress=False,
                extra_fields=[('Extra-field', 'my_extra_field')],
                cdx=True,
            ),
        )

        request = Request.new('http://example.com/')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'KITTEH DOGE')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)
            session.pre_response(response)
            session.response_data(response.header())
            session.response_data(response.body.content)
            session.response(response)

        _logger.info('FINISHED')

        warc_recorder.close()

        with open(warc_filename, 'rb') as in_file:
            warc_file_content = in_file.read()

        with open(cdx_filename, 'rb') as in_file:
            cdx_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'WARC-Type: warcinfo\r\n', warc_file_content)
        self.assertIn(b'Content-Type: application/warc-fields',
            warc_file_content)
        self.assertIn(b'WARC-Date: ', warc_file_content)
        self.assertIn(b'WARC-Record-ID: <urn:uuid:', warc_file_content)
        self.assertIn(b'WARC-Block-Digest: sha1:', warc_file_content)
        self.assertIn(b'WARC-Payload-Digest: sha1:', warc_file_content)
        self.assertIn(b'WARC-Type: request\r\n', warc_file_content)
        self.assertIn(b'WARC-Target-URI: http://', warc_file_content)
        self.assertIn(b'Content-Type: application/http;msgtype=request',
            warc_file_content)
        self.assertIn(b'WARC-Type: response', warc_file_content)
        self.assertIn(b'WARC-Concurrent-To: <urn:uuid:', warc_file_content)
        self.assertIn(b'Content-Type: application/http;msgtype=response',
            warc_file_content)
        self.assertIn(
            'Wpull/{0}'.format(wpull.version.__version__).encode('utf-8'),
            warc_file_content
        )
        self.assertIn(
            'Python/{0}'.format(
                wpull.util.python_version()).encode('utf-8'),
            warc_file_content
        )
        self.assertIn(b'Extra-Field: my_extra_field', warc_file_content)
        self.assertIn(b'GET / HTTP', warc_file_content)
        self.assertIn(b'KITTEH DOGE', warc_file_content)
        self.assertIn(b'FINISHED', warc_file_content)
        self.assertIn(b'WARC-Target-URI: urn:X-wpull:log', warc_file_content)
        self.assertIn(b'Content-Length:', warc_file_content)
        self.assertNotIn(b'Content-Length: 0', warc_file_content)

        cdx_lines = cdx_file_content.split(b'\n')
        cdx_labels = cdx_lines[0].strip().split(b' ')
        cdx_fields = cdx_lines[1].split(b' ')

        print(cdx_lines)

        self.assertEqual(3, len(cdx_lines))
        self.assertEqual(10, len(cdx_labels))
        self.assertEqual(9, len(cdx_fields))
        self.assertTrue(cdx_lines[0].startswith(b' CDX'))

        self.assertEqual(b'http://example.com/', cdx_fields[0])
        self.assertEqual(b'-', cdx_fields[2])
        self.assertEqual(b'200', cdx_fields[3])
        self.assertNotEqual(b'-', cdx_fields[4])
        self.assertNotEqual(b'0', cdx_fields[5])
        self.assertNotEqual(b'0', cdx_fields[6])
        self.assertEqual(
            os.path.basename(warc_filename), cdx_fields[7].decode('ascii'))

        length = int(cdx_fields[5])
        offset = int(cdx_fields[6])

        with open(warc_filename, 'rb') as in_file:
            in_file.seek(offset)
            data = in_file.read(length)

            assert len(data) == length

        self.assertEqual(b'WARC/1.0', data[:8])

        self.assertIn(b'KITTEH DOGE', data)

    def test_warc_recorder_max_size(self):
        file_prefix = 'asdf'
        cdx_filename = 'asdf.cdx'

        warc_recorder = WARCRecorder(
            file_prefix,
            params=WARCRecorderParams(
                compress=False,
                extra_fields=[('Extra-field', 'my_extra_field')],
                cdx=True, max_size=1,
            )
        )

        request = Request.new('http://example.com/1')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'KITTEH DOGE')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)
            session.pre_response(response)
            session.response_data(response.header())
            session.response_data(response.body.content)
            session.response(response)

        request = Request.new('http://example.com/2')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'DOGE KITTEH')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)
            session.pre_response(response)
            session.response_data(response.header())
            session.response_data(response.body.content)
            session.response(response)

        _logger.info('FINISHED')

        warc_recorder.close()

        with open('asdf-00000.warc', 'rb') as in_file:
            warc_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'WARC-Type: warcinfo', warc_file_content)
        self.assertIn(b'KITTEH DOGE', warc_file_content)

        with open('asdf-00001.warc', 'rb') as in_file:
            warc_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'WARC-Type: warcinfo', warc_file_content)
        self.assertIn(b'DOGE KITTEH', warc_file_content)

        with open(cdx_filename, 'rb') as in_file:
            cdx_file_content = in_file.read()

        cdx_lines = cdx_file_content.split(b'\n')
        cdx_labels = cdx_lines[0].strip().split(b' ')

        print(cdx_lines)

        self.assertEqual(4, len(cdx_lines))
        self.assertEqual(10, len(cdx_labels))

        self.assertIn(b'http://example.com/1', cdx_file_content)
        self.assertIn(b'http://example.com/2', cdx_file_content)

        with open('asdf-meta.warc', 'rb') as in_file:
            meta_file_content = in_file.read()

        self.assertIn(b'FINISHED', meta_file_content)

    def test_warc_recorder_rollback(self):
        warc_filename = 'asdf.warc'

        with open(warc_filename, 'wb') as warc_file:
            warc_file.write(b'a' * 10)

        warc_recorder = WARCRecorder(
            warc_filename,
            params=WARCRecorderParams(
                compress=False,
            )
        )

        request = Request.new('http://example.com/')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OK')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'KITTEH DOGE')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())

            class BadRecord(WARCRecord):
                def __init__(self, original_record):
                    super().__init__()
                    self.block_file = original_record.block_file
                    self.fields = original_record.fields

                def __iter__(self):
                    for dummy in range(1000):
                        yield b"where's my elephant?"
                    raise OSError('Oops')

            session._request_record = BadRecord(session._request_record)
            original_offset = os.path.getsize(warc_filename)

            try:
                session.request(request)
            except (OSError, IOError):
                new_offset = os.path.getsize(warc_filename)
                self.assertEqual(new_offset, original_offset)
            else:
                self.fail()

            _logger.debug('original offset {0}'.format(original_offset))

    def test_cdx_dedup(self):
        url_table = URLTable()
        warc_recorder = WARCRecorder(
            'asdf',
            params=WARCRecorderParams(
                compress=False, cdx=True, url_table=url_table
            )
        )

        url_table.add_visits([
            (
                'http://example.com/fennec',
                '<urn:uuid:8a534d31-bd06-4056-8a0f-bdc5fd611036>',
                'B62D734VFEKIDLFAB7TTSCSZF64BKAYJ'
            )
        ])

        request = Request.new('http://example.com/fennec')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OK')
        revisit_response_header_size = len(response.header())

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'kitbit')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)
            session.pre_response(response)
            session.response_data(response.header())
            session.response_data(response.body.content)
            session.response(response)

        request = Request.new('http://example.com/horse')
        request.address = ('0.0.0.0', 80)
        response = Response('HTTP/1.1', '200', 'OKaaaaaaaaaaaaaaaaaaaaaaaaaa')

        with wpull.util.reset_file_offset(response.body.content_file):
            response.body.content_file.write(b'kitbit')

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)
            session.pre_response(response)
            session.response_data(response.header())
            session.response_data(response.body.content)
            session.response(response)

        _logger.info('FINISHED')

        warc_recorder.close()

        with open('asdf.warc', 'rb') as in_file:
            warc_file_content = in_file.read()

        with open('asdf.cdx', 'rb') as in_file:
            cdx_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'WARC-Type: revisit\r\n', warc_file_content)
        self.assertIn(
            b'WARC-Refers-To: '
                b'<urn:uuid:8a534d31-bd06-4056-8a0f-bdc5fd611036>\r\n',
            warc_file_content
        )
        self.assertIn(b'WARC-Truncated: length\r\n', warc_file_content)
        self.assertIn(
            b'WARC-Profile: http://netpreserve.org/warc/1.0/revisit/'
                b'identical-payload-digest\r\n',
            warc_file_content
        )
        self.assertIn(
            b'Content-Length: ' +
                str(revisit_response_header_size).encode('ascii') + b'\r\n',
            warc_file_content
        )
        self.assertIn(
            b'WARC-Target-URI: http://example.com/fennec\r\n',
            warc_file_content
        )
        self.assertIn(
            b'WARC-Target-URI: http://example.com/horse\r\n', warc_file_content
        )
        self.assertEqual(
            1,
            warc_file_content.count(b'kitbit')
        )

        self.assertIn(b'http://example.com/horse ', cdx_file_content)
