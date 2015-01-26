import json
import logging
import os.path
import subprocess
import tempfile

import namedlist
import trollius
from trollius.coroutines import From, Return

from wpull.driver.process import Process
import wpull.util


_logger = logging.getLogger(__name__)


PhantomJSDriverParams = namedlist.namedtuple(
    'PhantomJSDriverParamsType', [
        'url',
        ('snapshot_paths', []),
        ('wait_time', 1),
        ('num_scrolls', 10),
        ('smart_scroll', True),
        ('snapshot', True),
        ('viewport_size', (1200, 1920)),
        ('paper_size', (2400, 3840)),
        ('event_log_filename', None),
        ('action_log_filename', None),
        ('custom_headers', {}),
        ('page_settings', {}),
    ]
)
'''PhantomJS Driver parameters

Attributes:
    url (str): URL of page to fetch.
    snapshot_type (list): List of filenames. Accepted extensions are html,
        pdf, png, gif.
    wait_time (float): Time between page scrolls.
    num_scrolls (int): Maximum number of scrolls.
    smart_scroll (bool): Whether to stop scrolling if number of
        requests & responses do not change.
    snapshot (bool): Whether to take snapshot files.
    viewport_size (tuple): Width and height of the page viewport.
    paper_size (tuple): Width and height of the paper size.
    event_log_filename (str): Path to save page events.
    action_log_filename (str): Path to save page action manipulation events.
    custom_headers (dict): Custom HTTP request headers.
    page_settings (dict): Page settings.
'''


class PhantomJSDriver(Process):
    '''PhantomJS processing.

    Args:
        exe_path (str): Path of the PhantomJS executable.
        extra_args (list): Additional arguments for PhantomJS. Most likely,
            you'll want to pass proxy settings for capturing traffic.
        params (:class:`PhantomJSDriverParams`): Parameters for controlling
            the processing pipeline.

    This class launches PhantomJS that scrolls and saves snapshots. It can
    only be used once per URL.
    '''
    def __init__(self, exe_path='phantomjs', extra_args=None, params=None):
        script_path = wpull.util.get_package_filename('driver/phantomjs.js')

        self._config_file = tempfile.NamedTemporaryFile(
            prefix='wpull-', suffix='.json', delete=False
        )

        args = [exe_path] + (extra_args or []) + [script_path, self._config_file.name]
        super().__init__(args, stderr_callback=self._stderr_callback)

        self._params = params

    def _stderr_callback(self, line):
        _logger.warning(line.decode('utf-8', 'replace').rstrip())

    @trollius.coroutine
    def start(self, use_atexit=True):
        _logger.debug('PhantomJS start.')

        self._write_config()

        yield From(super().start(use_atexit))

    def _write_config(self):
        '''Write the parameters to a file for PhantomJS to read.'''
        param_dict = {
            'url': self._params.url,
            'snapshot_paths': self._params.snapshot_paths,
            'wait_time': self._params.wait_time,
            'num_scrolls': self._params.num_scrolls,
            'smart_scroll': self._params.smart_scroll,
            'snapshot': self._params.snapshot,
            'viewport_width': self._params.viewport_size[0],
            'viewport_height': self._params.viewport_size[1],
            'paper_width': self._params.paper_size[0],
            'paper_height': self._params.paper_size[1],
            'custom_headers': self._params.custom_headers,
            'page_settings': self._params.page_settings,
        }

        if self._params.event_log_filename:
            param_dict['event_log_filename'] = \
                os.path.abspath(self._params.event_log_filename)

        if self._params.action_log_filename:
            param_dict['action_log_filename'] = \
                os.path.abspath(self._params.action_log_filename)

        config_text = json.dumps(param_dict)

        self._config_file.write(config_text.encode('utf-8'))

        # Close it so the phantomjs process can read it on Windows
        self._config_file.close()

    def close(self):
        _logger.debug('Terminate phantomjs process.')
        super().close()

        if os.path.exists(self._config_file.name):
            os.remove(self._config_file.name)

def get_version(exe_path='phantomjs'):
    '''Get the version string of PhantomJS.'''
    process = subprocess.Popen(
        [exe_path, '--version'],
        stdout=subprocess.PIPE
    )
    version_string = process.communicate()[0]
    return version_string.decode().strip()
