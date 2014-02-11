# encoding=utf-8
import gzip
import io
import logging
import os.path
import tempfile

from wpull.backport.testing import unittest
from wpull.http import Request, Response
from wpull.recorder import WARCRecorder
import wpull.util
import wpull.version


_logger = logging.getLogger(__name__)


class RecorderTest(unittest.TestCase):
    def test_warc_recorder(self):
        temp_file = tempfile.NamedTemporaryFile()
        warc_recorder = WARCRecorder(
            temp_file.name, compress=False,
            extra_fields=[('Extra-field', 'my_extra_field')],
            cdx_filename=temp_file.name + '.cdx',
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

        with open(temp_file.name, 'rb') as in_file:
            warc_file_content = in_file.read()

        with open(temp_file.name + '.cdx', 'rb') as in_file:
            cdx_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'WARC-Type: warcinfo', warc_file_content)
        self.assertIn(b'Content-Type: application/warc-fields',
            warc_file_content)
        self.assertIn(b'WARC-Date: ', warc_file_content)
        self.assertIn(b'WARC-Record-ID: <urn:uuid:', warc_file_content)
        self.assertIn(b'WARC-Block-Digest: sha1:', warc_file_content)
        self.assertIn(b'WARC-Payload-Digest: sha1:', warc_file_content)
        self.assertIn(b'WARC-Type: request', warc_file_content)
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
            'Python/{0}'.format(wpull.util.python_version()).encode('utf-8'),
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
            os.path.basename(temp_file.name), cdx_fields[7].decode('ascii'))

        length = int(cdx_fields[5])
        offset = int(cdx_fields[6])

        with open(temp_file.name, 'rb') as in_file:
            in_file.seek(offset)
            data = in_file.read(length)

            assert len(data) == length

        self.assertEqual(b'WARC/1.0', data[:8])

        self.assertIn(b'KITTEH DOGE', data)
