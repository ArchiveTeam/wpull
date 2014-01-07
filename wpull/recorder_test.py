# encoding=utf-8
import tempfile

from wpull.backport.testing import unittest
from wpull.http import Request
from wpull.recorder import WARCRecorder
import wpull.util
import wpull.version


class RecorderTest(unittest.TestCase):
    def test_warc_recorder(self):
        temp_file = tempfile.NamedTemporaryFile()
        warc_recorder = WARCRecorder(temp_file.name, compress=False,
            extra_fields=[('Extra-field', 'my_extra_field')])

        request = Request.new('http://example.com/')
        request.address = ('0.0.0.0', 80)

        with warc_recorder.session() as session:
            session.pre_request(request)
            session.request_data(request.header())
            session.request(request)

        warc_recorder.close()

        with open(temp_file.name, 'rb') as in_file:
            warc_file_content = in_file.read()

        self.assertTrue(warc_file_content.startswith(b'WARC/1.0'))
        self.assertIn(b'warcinfo', warc_file_content)
        self.assertIn(
            'Wpull/{0}'.format(wpull.version.__version__).encode('utf-8'),
            warc_file_content
        )
        self.assertIn(
            'Python/{0}'.format(wpull.util.python_version()).encode('utf-8'),
            warc_file_content
        )
        self.assertIn(b'my_extra_field', warc_file_content)
        self.assertIn(b'GET / HTTP', warc_file_content)
