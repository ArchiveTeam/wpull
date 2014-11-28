import abc
import json
import logging
import subprocess
import atexit
import errno
import time

from trollius import From
import trollius

from wpull.backport.logging import BraceMessage as __


_logger = logging.getLogger(__name__)


class RPCProcess(object):
    def __init__(self, proc_args, message_callback):
        self._proc_args = proc_args
        self._process = None
        self._message_callback = message_callback
        self._stderr_reader = None
        self._stdout_reader = None

    @trollius.coroutine
    def start(self, use_atexit=True):
        process_future = trollius.create_subprocess_exec(
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            *self._proc_args
            )
        self._process = yield From(process_future)

        self._stderr_reader = trollius.async(self._read_stderr())
        self._stdout_reader = trollius.async(self._read_stdout())

        if use_atexit:
            atexit.register(self.close)

    def close(self):
        '''Terminate or kill the subprocess.

        This function is blocking.
        '''
        if not self._process:
            return

        if self._process.returncode is not None:
            return

        try:
            self._process.terminate()
        except OSError as error:
            if error.errno != errno.ESRCH:
                raise

        for dummy in range(10):
            if self._process.returncode is not None:
                return

            time.sleep(0.05)

        try:
            self._process.kill()
        except OSError as error:
            if error.errno != errno.ESRCH:
                raise

    @trollius.coroutine
    def _read_stdout(self):
        while True:
            line = yield From(self._process.stdout.readline())

            _logger.debug('Read stdout line %s', repr(line))

            if not line:
                break

            if line.startswith(b'!RPC '):
                message = json.loads(line[5:].decode('utf-8'))
                return_value = self._message_callback(message)

                if return_value is not None:
                    yield From(self.send_message(return_value))

    @trollius.coroutine
    def _read_stderr(self):
        while True:
            line = yield From(self._process.stderr.readline())

            if not line:
                break

            _logger.warning(__(
                _('Subprocess: {message}'),
                message=line.rstrip()
            ))

    @trollius.coroutine
    def send_message(self, message):
        self._process.stdin.write(b'!RPC ')
        self._process.stdin.write(json.dumps(message).encode('utf-8'))
        self._process.stdin.write(b'\n')
        yield From(self._process.stdin.drain())
