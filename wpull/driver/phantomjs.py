# encoding=utf-8
'''PhantomJS wrapper.'''
import atexit
import contextlib
import json
import logging
import subprocess
import time
import uuid
import errno

import trollius
from trollius.coroutines import From, Return

from wpull.backport.logging import BraceMessage as __
from wpull.driver.process import RPCProcess
import wpull.observer
import wpull.util


_logger = logging.getLogger(__name__)


class PhantomJSRPCError(OSError):
    '''Error during RPC call to PhantomJS.'''
    pass


class PhantomJSRPCTimedOut(PhantomJSRPCError):
    '''RPC call timed out.'''


class PhantomJSDriver(object):
    '''PhantomJS RPC wrapper.

    Args:
        exe_path (str): Path of the PhantomJS executable.

    This class automatically manages the life of the PhantomJS process. It
    will automatically terminate the process on interpreter shutdown.

    Attributes:
        page_event_handlers (dict): A mapping of event names to callback
            functions.

    The messages passed are in the JSON format.
    '''
    def __init__(self, exe_path='phantomjs', extra_args=None,
                 page_settings=None, default_headers=None):

        script_path = wpull.util.get_package_filename('driver/phantomjs.js')
        args = [exe_path] + (extra_args or []) + [script_path]

        self._process = RPCProcess(args, self._message_callback)

        self._page_settings = page_settings
        self._default_headers = default_headers

        self.page_event_handlers = {}

        self._message_out_queue = trollius.Queue()
        self._message_in_queue = trollius.Queue()

        self._is_setup = False

    @trollius.coroutine
    def start(self):
        _logger.debug('PhantomJS setup.')

        assert not self._is_setup
        self._is_setup = True

        yield From(self._process.start())

    def _message_callback(self, message):
        event_name = message['event']

        if event_name == 'poll':
            try:
                return self._message_out_queue.get_nowait()
            except trollius.QueueEmpty:
                return {'command': None}
        elif event_name == 'reply':
            self._message_in_queue.put_nowait(message)
        else:
            return self._event_callback(message)

    def _event_callback(self, message):
        name = message['event']

        if name in self.page_event_handlers:
            value = self.page_event_handlers[name](message)
        else:
            value = None

        return {'value': value}

    def close(self):
        '''Terminate the PhantomJS process.'''
        if self.return_code is None:
            _logger.debug('Terminate phantomjs process.')
            self._process.close()

    @trollius.coroutine
    def send_command(self, command, **kwargs):
        message = {'command': command}
        message.update(dict(**kwargs))
        yield From(self._message_out_queue.put(message))

        reply = yield From(self._message_in_queue.get())

        raise Return(reply['value'])

    @trollius.coroutine
    def open_page(self, url, viewport_size=(1024, 768), paper_size=(1024, 768)):
        yield From(self.send_command('new_page'))
        yield From(self.send_command('set_page_size',
                                     viewport_width=viewport_size[0],
                                     viewport_height=viewport_size[1],
                                     paper_width=paper_size[0],
                                     paper_height=paper_size[1]
        ))
        yield From(self._apply_default_settings())
        yield From(self.send_command('open_url', url=url))

    @trollius.coroutine
    def _apply_default_settings(self):
        if self._page_settings:
            yield From(
                self.send_command('set_page_settings',
                                  settings=self._page_settings)
            )

        if self._default_headers:
            yield From(
                self.send_command('set_page_custom_headers',
                                  headers=self._default_headers)
            )

    @trollius.coroutine
    def close_page(self):
        yield From(self.send_command('close_page'))

    @trollius.coroutine
    def snapshot(self, path):
        yield From(self.send_command('render_page', path=path))

    @trollius.coroutine
    def scroll_to(self, x, y):
        yield From(self.send_command('scroll_page', x=x, y=y))

    @trollius.coroutine
    def get_page_url(self):
        url = yield From(self.send_command('get_page_url'))
        raise Return(url)

    @property
    def return_code(self):
        '''Return the exit code of the PhantomJS process.'''
        if self._process and self._process.process:
            return self._process.process.returncode


class PhantomJSPool(object):
    '''PhantomJS driver pool
    '''
    def __init__(self, exe_path='phantomjs', extra_args=None,
                 page_settings=None, default_headers=None):
        self._ready = set()
        self._busy = set()
        self._exe_path = exe_path
        self._extra_args = extra_args
        self._page_settings = page_settings
        self._default_headers = default_headers

    # def test_client_exe(self):
    #     '''Raise an error if PhantomJS executable is not found.'''
    #     remote = PhantomJSRemote(self._exe_path)
    #     remote.close()

    @property
    def drivers_ready(self):
        '''Return the drivers that are not used.'''
        return frozenset(self._ready)

    @property
    def drivers_busy(self):
        '''Return the drivers that are currently used.'''
        return frozenset(self._busy)

    def check_out(self):
        '''Return a driver.'''
        while True:
            if not self._ready:
                _logger.debug('Creating new driver')

                driver = PhantomJSDriver(
                    self._exe_path,
                    extra_args=self._extra_args,
                    page_settings=self._page_settings,
                    default_headers=self._default_headers,
                    )
                break
            else:
                driver = self._ready.pop()

                # Check if phantomjs has crashed
                if driver.return_code is None:
                    break
                else:
                    driver.close()

        self._busy.add(driver)

        return driver

    def check_in(self, driver):
        '''Check in a driver after using it.'''
        self._busy.remove(driver)

        if driver.return_code is None:
            self._ready.add(driver)
        else:
            driver.close()

    @contextlib.contextmanager
    def session(self):
        '''Return a PhantomJS Remote within a context manager.'''

        driver = self.check_out()

        assert driver.return_code is None

        try:
            yield driver
        finally:
            self.check_in(driver)

    def close(self):
        '''Close all drivers.'''
        for driver in self._busy:
            driver.close()

        self._busy.clear()

        for driver in self._ready:
            driver.close()

        self._ready.clear()

    def clean(self):
        '''Clean up drivers that are closed.'''
        for driver in self._ready:
            if driver.return_code is not None:
                driver.close()


def get_version(exe_path='phantomjs'):
    '''Get the version string of PhantomJS.'''
    process = subprocess.Popen(
        [exe_path, '--version'],
        stdout=subprocess.PIPE
    )
    version_string = process.communicate()[0]
    return version_string.decode().strip()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    phantomjs = PhantomJSDriver()

    trollius.get_event_loop().run_forever()
