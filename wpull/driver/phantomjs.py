# encoding=utf-8
'''PhantomJS wrapper.'''
import contextlib
import logging
import subprocess
import uuid

import trollius
from trollius.coroutines import From, Return

from wpull.backport.logging import BraceMessage as __
from wpull.driver.process import RPCProcess
import wpull.observer
import wpull.util


_logger = logging.getLogger(__name__)


class PhantomJSRPCError(OSError):
    '''Error during RPC call to PhantomJS.'''


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
                 page_settings=None, default_headers=None, rpc_timeout=60):

        script_path = wpull.util.get_package_filename('driver/phantomjs.js')
        self._args = [exe_path] + (extra_args or []) + [script_path]

        self._process = None

        self._page_settings = page_settings
        self._default_headers = default_headers
        self._rpc_timeout = rpc_timeout

        self.page_event_handlers = {}

        self._message_out_queue = trollius.Queue()
        self._message_in_queue = trollius.Queue()

    @trollius.coroutine
    def start(self):
        '''Start the PhantomJS executable.

        Always call this first.

        Coroutine.
        '''
        _logger.debug('PhantomJS setup.')

        if self._process and self._process.process.returncode is None:
            return

        self._process = RPCProcess(self._args, self._message_callback)

        yield From(self._process.start())

    def _message_callback(self, message):
        '''Callback for a RPC message.'''
        event_name = message['event']
        _logger.debug(__('Message callback {}', event_name))

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
        '''Callback for a page event.'''
        name = message['event']
        _logger.debug(__('Event callback {}', name))

        if name in self.page_event_handlers:
            value = self.page_event_handlers[name](message)
        else:
            value = None

        return {'value': value}

    def close(self):
        '''Terminate the PhantomJS process.'''
        if self._process and self.return_code is None:
            _logger.debug('Terminate phantomjs process.')
            self._process.close()

    @trollius.coroutine
    def send_command(self, command, **kwargs):
        '''Send a RPC command.'''
        message_id = uuid.uuid4().hex
        _logger.debug(__('Send command {} {}', command, message_id))

        message = {'command': command, 'message_id': message_id}
        message.update(dict(**kwargs))
        yield From(self._message_out_queue.put(message))

        try:
            reply = yield From(trollius.wait_for(self._message_in_queue.get(), self._rpc_timeout))
        except trollius.TimeoutError as error:
            self.close()
            raise PhantomJSRPCTimedOut(
                'Send command {} timed out'.format(repr(command))) from error

        _logger.debug(__('Command reply {} {}', command, reply))

        raise Return(reply['value'])

    @trollius.coroutine
    def open_page(self, url, viewport_size=(1024, 768), paper_size=(1024, 768)):
        '''Create a page and load the URL.'''
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
        '''Apply default settings and headers.'''
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
        '''Close and delete the page.'''
        yield From(self.send_command('close_page'))

    @trollius.coroutine
    def snapshot(self, path):
        '''Generate a snapshot file.'''
        yield From(self.send_command('render_page', path=path))

    @trollius.coroutine
    def scroll_to(self, x, y):
        '''Scroll the page to given location.'''
        yield From(self.send_command('scroll_page', x=x, y=y))

    @trollius.coroutine
    def send_click(self, x, y, button='left'):
        '''Mouse click on a position.'''
        yield From(self.send_command('click', x=x, y=y, button=button))

    @trollius.coroutine
    def send_key(self, key, modifier=0):
        '''Send a keyboard command.'''
        yield From(self.send_command('key', key=key, modifier=modifier))

    @trollius.coroutine
    def get_page_url(self):
        '''Return the current page URL.'''
        url = yield From(self.send_command('get_page_url'))
        raise Return(url)

    @trollius.coroutine
    def is_page_dynamic(self):
        '''Return whether the page is dynamic.'''
        result = yield From(self.send_command('is_page_dynamic'))
        raise Return(result)


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
