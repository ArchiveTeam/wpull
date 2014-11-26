import abc
import json
import logging
import subprocess
import atexit

from trollius import From
import trollius

from wpull.backport.logging import BraceMessage as __


_logger = logging.getLogger(__name__)


class BaseDriverProcess(object, metaclass=abc.ABCMeta):
    def __init__(self, proc_args):
        self._proc_args = proc_args
        self._process = None

    @trollius.coroutine
    def start(self, use_atexit=True):
        process_future = trollius.create_subprocess_exec(
            self._proc_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            )
        self._process = yield From(process_future)

        if use_atexit:
            atexit.atext(self.close)

    def close(self):
        self._process.terminate()
        self._process.kill()

    @trollius.coroutine
    def _read_stdout(self):
        while True:
            line = yield From(self._process.stdout.readline())

            if not line:
                break

            if line.startswith(b'!RPC '):
                message = json.loads(line[:5].decode('utf-8'))
                return_value = self._handle_event(
                    message['_event_name'], message
                )

                self._process.stdin.write(b'!RPC ')
                self._process.stdin.write(json.dumps(return_value))
                self._process.stdin.write(b'\n')
                yield From(self._process.stdin.drain())

    @trollius.coroutine
    def _read_stderr(self):
        while True:
            line = yield From(self._process.readline())

            if not line:
                break

            _logger.warning(__(
                _('Subprocess: {message}'),
                message=line.rstrip()
            ))

    @abc.abstractmethod
    def _handle_event(self, event_name, properties):
        return None
