import json
import logging
import os.path
import subprocess
import tempfile
from typing import Any

import asyncio

from wpull.driver.process import Process
import wpull.util


_logger = logging.getLogger(__name__)

from typing import NamedTuple
class PhantomJSDriverParams(NamedTuple):
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
    url: str
    snapshot_paths: Any = []
    wait_time: Any = 1
    num_scrolls: Any = 10
    smart_scroll: Any = True
    snapshot: Any = True
    viewport_size: Any = (1200, 1920)
    paper_size: Any = (2400, 3840)
    event_log_filename: Any = None
    action_log_filename: Any = None
    custom_headers: Any = {}
    page_settings: Any = {}


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
            prefix='tmp-wpull-', suffix='.json', delete=False
        )

        args = [exe_path] + (extra_args or []) + [script_path, self._config_file.name]
        super().__init__(args, stderr_callback=self._stderr_callback)

        self._params = params

    @asyncio.coroutine
    def _stderr_callback(self, line):
        _logger.warning(line.decode('utf-8', 'replace').rstrip())

    @asyncio.coroutine
    def start(self, use_atexit=True):
        _logger.debug('PhantomJS start.')

        self._write_config()

        yield from super().start(use_atexit)

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
    version_string = version_string.decode().strip()

    assert ' ' not in version_string, version_string

    return version_string
