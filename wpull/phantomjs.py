# encoding=utf-8
'''PhantomJS wrapper.'''
import atexit
import contextlib
import json
import logging
import subprocess
import time
import uuid

import trollius
from trollius.coroutines import From, Return

from wpull.backport.logging import BraceMessage as __
import wpull.observer
import wpull.util


_logger = logging.getLogger(__name__)


class PhantomJSRPCError(OSError):
    '''Error during RPC call to PhantomJS.'''
    pass


class PhantomJSRPCTimedOut(PhantomJSRPCError):
    '''RPC call timed out.'''


class PhantomJSRemote(object):
    '''PhantomJS RPC wrapper.

    Args:
        exe_path (str): Path of the PhantomJS executable.

    This class automatically manages the life of the PhantomJS process. It
    will automatically terminate the process on interpreter shutdown.

    Attributes:
        page_observer: An instance of :class:`.observer.Observer` that is
            fired whenever a page event occurs. The argument passed to the
            listener is a RPC Info ``dict``.
        resource_counter: An instance of :class:`ResourceCounter()`.

    The messages passed are in the JSON format.
    '''
    def __init__(self, exe_path='phantomjs', extra_args=None,
                 page_settings=None, default_headers=None,
                 rewrite_enabled=True):
        self._exe_path = exe_path
        self._extra_args = extra_args
        self._page_settings = page_settings
        self._default_headers = default_headers
        self._rewrite_enabled = rewrite_enabled

        self.page_observer = wpull.observer.Observer()
        self.resource_counter = ResourceCounter()

        self._rpc_out_queue = trollius.Queue()

        self._rpc_reply_map = {}

        self._subproc = None
        self._is_setup = False

    @trollius.coroutine
    def _setup(self):
        _logger.debug('PhantomJS setup.')

        assert not self._is_setup
        self._is_setup = True
        yield From(self._create_subprocess())

        trollius.async(self._read_stdout())
        trollius.async(self._write_stdin())

        yield From(self._apply_default_settings())

        if self._rewrite_enabled:
            yield From(self.set('rewriteEnabled', True))

    @trollius.coroutine
    def _create_subprocess(self):
        script_path = wpull.util.get_package_filename('phantomjs.js')
        args = [self._exe_path] + (self._extra_args or []) + [script_path]

        self._subproc = yield From(
            trollius.create_subprocess_exec(*args,
                                            stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE)
        )

        atexit.register(self._atexit_kill_subprocess)

        _logger.debug('PhantomJS subprocess created.')

    @trollius.coroutine
    def _read_stdout(self):
        _logger.debug('Begin reading stdout.')
        multiline_list = None

        while self._subproc.returncode is None:
            line = yield From(self._subproc.stdout.readline())

            if line[-1:] != b'\n':
                break

            if line.startswith(b'!RPC!'):
                self._parse_message(line[5:])
            elif line.startswith(b'!RPC['):
                multiline_list = [line[5:].rstrip()]
            elif line.startswith(b'!RPC+'):
                multiline_list.append(line[5:].rstrip())
            elif line.startswith(b'!RPC]'):
                self._parse_message(b''.join(multiline_list))
                multiline_list = None
            else:
                _logger.debug(
                    __('PhantomJS: {0}', line.decode('utf-8').rstrip())
                )

        _logger.debug(__('End reading stdout. returncode {0}',
                         self._subproc.returncode))

    def _parse_message(self, message):
        try:
            rpc_info = json.loads(message.decode('utf-8'))
        except ValueError:
            _logger.exception('Error decoding message.')
        else:
            if 'event' in rpc_info:
                self._process_resource_counter(rpc_info)
                self.page_observer.notify(rpc_info)
            else:
                self._process_rpc_result(rpc_info)

    @trollius.coroutine
    def _write_stdin(self):
        _logger.debug('Begin writing stdin.')

        while self._subproc.returncode is None:
            try:
                # XXX: we are nonblocking because wait_for seems to lose items
                rpc_info = self._rpc_out_queue.get_nowait()
            except trollius.QueueEmpty:
                yield From(trollius.sleep(0.1))
            else:
                self._subproc.stdin.write(b'!RPC!')
                self._subproc.stdin.write(json.dumps(rpc_info).encode('utf-8'))

            # XXX: always force feed so phantomjs doesn't block on readline
            self._subproc.stdin.write(b'\n')
            yield From(self._subproc.stdin.drain())

        _logger.debug('End writing stdin.')

    @trollius.coroutine
    def _apply_default_settings(self):
        if self._page_settings:
            yield From(
                self.call('setDefaultPageSettings', self._page_settings)
            )

        if self._default_headers:
            yield From(
                self.call('setDefaultPageHeaders', self._default_headers)
            )

    def close(self):
        '''Terminate the PhantomJS process.'''
        if not self._subproc:
            return

        if self._subproc.returncode is not None:
            return

        self._subproc.terminate()

    @property
    def return_code(self):
        '''Return the exit code of the PhantomJS process.'''
        if self._subproc:
            return self._subproc.returncode

    def _atexit_kill_subprocess(self):
        '''Terminate or kill the subprocess.

        This function is blocking.
        '''
        if not self._subproc:
            return

        if self._subproc.returncode is not None:
            return

        self._subproc.terminate()

        for dummy in range(10):
            if self._subproc.returncode is not None:
                return

            time.sleep(0.05)

        self._subproc.kill()

    @trollius.coroutine
    def call(self, name, *args, timeout=10):
        '''Call a function.

        Args:
            name (str): The name of the function.
            args: Any arguments for the function.
            timeout (float): Time out in seconds.

        Returns:
            something

        Raises:
            PhantomJSRPCError
        '''
        rpc_info = {
            'action': 'call',
            'name': name,
            'args': args,
        }
        result = yield From(self._rpc_exec(rpc_info, timeout=timeout))
        raise Return(result)

    @trollius.coroutine
    def set(self, name, value, timeout=10):
        '''Set a variable value.

        Args:
            name (str): The name of the variable.
            value: The value.
            timeout (float): Time out in seconds.

        Raises:
            PhantomJSRPCError
        '''
        rpc_info = {
            'action': 'set',
            'name': name,
            'value': value,
        }
        result = yield From(self._rpc_exec(rpc_info, timeout=timeout))
        raise Return(result)

    @trollius.coroutine
    def eval(self, text, timeout=10):
        '''Get a variable value or evaluate an expression.

        Args:
            text (str): The variable name or expression.

        Returns:
            something

        Raises:
            PhantomJSRPCError
        '''
        rpc_info = {
            'action': 'eval',
            'text': text,
        }
        result = yield From(self._rpc_exec(rpc_info, timeout=timeout))
        raise Return(result)

    @trollius.coroutine
    def wait_page_event(self, event_name, timeout=120):
        '''Wait until given event occurs.

        Args:
            event_name (str): The event name.
            timeout (float): Time out in seconds.

        Returns:
            dict:
        '''
        event_lock = trollius.Event()

        def page_event_cb(rpc_info):
            if rpc_info['event'] == event_name:
                event_lock.rpc_info = rpc_info
                event_lock.set()

        self.page_observer.add(page_event_cb)

        try:
            yield From(trollius.wait_for(event_lock.wait(), timeout=timeout))
        except trollius.TimeoutError as error:
            raise PhantomJSRPCTimedOut('Waiting for event timed out.') \
                from error

        self.page_observer.remove(page_event_cb)

        raise Return(event_lock.rpc_info)

    @trollius.coroutine
    def _rpc_exec(self, rpc_info, timeout=None):
        '''Execute the RPC and return.

        Returns:
            something

        Raises:
            PhantomJSRPCError
        '''
        if not self._is_setup:
            yield From(self._setup())

        while not self._subproc:
            # This case occurs when using trollius.async() which causes
            # things to be out of order even though it appears that
            # the subprocess should have been set up already.
            # FIXME: Maybe we should use a lock
            _logger.debug('Waiting for PhantomJS subprocess.')
            yield From(trollius.sleep(0.1))

        if 'id' not in rpc_info:
            rpc_info['id'] = uuid.uuid4().hex

        if self._subproc.returncode is not None:
            raise PhantomJSRPCError('PhantomJS process has quit unexpectedly.')

        event_lock = yield From(self._put_rpc_info(rpc_info))

        try:
            yield From(trollius.wait_for(event_lock.wait(), timeout=timeout))
            rpc_call_info = event_lock.rpc_info
        except trollius.TimeoutError as error:
            self._cancel_rpc_info(rpc_info)
            raise PhantomJSRPCTimedOut('RPC timed out.') from error

        if 'error' in rpc_call_info:
            raise PhantomJSRPCError(rpc_call_info['error']['stack'])
        elif 'result' in rpc_call_info:
            raise Return(rpc_call_info['result'])

    @trollius.coroutine
    def _put_rpc_info(self, rpc_info):
        '''Put the request RPC info into the out queue and reply mapping.

        Returns:
            Event: An instance of :class:`trollius.Event`.
        '''
        event_lock = trollius.Event()
        self._rpc_reply_map[rpc_info['id']] = event_lock

        _logger.debug(__('Put RPC. {0}', rpc_info))

        yield From(self._rpc_out_queue.put(rpc_info))

        raise Return(event_lock)

    def _cancel_rpc_info(self, rpc_info):
        '''Cancel the request RPC.'''
        self._rpc_reply_map.pop(rpc_info['id'], None)

    def _process_rpc_result(self, rpc_info):
        '''Match the reply and invoke the Event.'''
        answer_id = rpc_info['reply_id']
        event_lock = self._rpc_reply_map.pop(answer_id, None)

        if event_lock:
            event_lock.rpc_info = rpc_info
            event_lock.set()

    def _process_resource_counter(self, rpc_info):
        '''Check event type and increment counter as needed.'''
        event_name = rpc_info['event']

        if event_name == 'resource_requested':
            self.resource_counter.pending += 1
        elif (event_name == 'resource_received'
              and rpc_info['response']['stage'] == 'end'):
            self.resource_counter.pending -= 1
            self.resource_counter.loaded += 1
        elif event_name == 'resource_error':
            self.resource_counter.pending -= 1
            self.resource_counter.error += 1


class PhantomJSClient(object):
    '''PhantomJS Remote Client.

    This class wraps the components of Wpull to the Remote. A pool of Remotes
    are used.
    '''
    def __init__(self, proxy_address, exe_path='phantomjs', extra_args=None,
                 page_settings=None, default_headers=None):
        self._remotes_ready = set()
        self._remotes_busy = set()
        self._exe_path = exe_path
        self._extra_args = extra_args
        self._page_settings = page_settings
        self._default_headers = default_headers
        self._proxy_address = proxy_address

    def test_client_exe(self):
        '''Raise an error if PhantomJS executable is not found.'''
        remote = PhantomJSRemote(self._exe_path)
        remote.close()

    @property
    def remotes_ready(self):
        '''Return the Remotes that are not used.'''
        return frozenset(self._remotes_ready)

    @property
    def remotes_busy(self):
        '''Return the Remotes that are currently used.'''
        return frozenset(self._remotes_busy)

    @contextlib.contextmanager
    def remote(self):
        '''Return a PhantomJS Remote within a context manager.'''
        while True:
            if not self._remotes_ready:
                extra_args = [
                    '--proxy={0}'.format(self._proxy_address)
                ]

                if self._extra_args:
                    extra_args.extend(self._extra_args)

                _logger.debug(__(
                    'Creating new remote with proxy {0}',
                    self._proxy_address
                ))

                remote = PhantomJSRemote(
                    self._exe_path,
                    extra_args=extra_args,
                    page_settings=self._page_settings,
                    default_headers=self._default_headers,
                )
                break
            else:
                remote = self._remotes_ready.pop()

                # Check if phantomjs has crashed
                if remote.return_code is None:
                    break
                else:
                    remote.close()

        self._remotes_busy.add(remote)

        assert remote.return_code is None

        try:
            yield remote
        finally:
            remote.page_observer.clear()
            remote.resource_counter.reset()

            self._remotes_busy.remove(remote)

            def put_back_remote():
                # FIXME: catch exception
                trollius.async(remote.call('resetPage'))
                self._remotes_ready.add(remote)

            if remote.return_code is None:
                trollius.get_event_loop().call_soon(put_back_remote)
            else:
                remote.close()

    def close(self):
        '''Close all remotes.'''
        for remote in self._remotes_busy:
            remote.close()

        self._remotes_busy.clear()

        for remote in self._remotes_ready:
            remote.close()

        self._remotes_ready.clear()


class ResourceCounter(object):
    '''Resource counter.

    Attributes:
        pending (int): Number of resources that are downloading.
        loaded (int): Number of resources that have downloaded.
        error (int): Number of resources that have failed to download.
    '''
    def __init__(self):
        self.pending = 0
        self.loaded = 0
        self.error = 0

    def reset(self):
        '''Reset the counter to 0.'''
        self.pending = 0
        self.loaded = 0
        self.error = 0

    def values(self):
        '''Return the counter as an tuple.

        Returns:
            tuple: (pending, loaded, error)
        '''
        return (self.pending, self.loaded, self.error)


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

    phantomjs = PhantomJSRemote()

    trollius.get_event_loop().run_forever()
