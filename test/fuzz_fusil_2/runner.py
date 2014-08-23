'''Fuzz tester.

This script to be run under Python 2.

Install dependencies via pip::

    pip install fusil python-ptrace
'''
import os.path
import random
import sys

from fusil.application import Application
from fusil.process.create import ProjectProcess
from fusil.process.stdout import WatchStdout
from fusil.process.watch import WatchProcess


class Fuzzer(Application):
    def setupProject(self):
        self.project.debugger.enabled = False
        port = 8848
        seed = random.randint(0, 60000)

        server_process = ProjectProcess(
            self.project,
            [
                'python3', '-m', 'huhhttp',
                '--port', str(port),
                '--seed', str(seed),
                '--fuzz-period', '500',
                '--restart-interval', '10000',
            ],
        )
        WatchProcess(server_process)

        process = ProjectProcess(
            self.project,
            [
                'python3', '-m', 'wpull',
                '127.0.0.1:{0}'.format(port),
                '--timeout', '5',
                '--warc-file', 'fusil-test',
                '-r',
                '--no-verbose',
                '--page-requisites',
                '--delete-after',
            ],
        )

        process.env.set(
            'PYTHONPATH',
            os.path.join(
                os.path.abspath(os.path.dirname(__file__)), '..', '..')
            )

        WatchProcess(process, exitcode_score=0.45)
        stdout_watcher = WatchStdout(process)
        stdout_watcher.max_nb_line = None
        stdout_watcher.ignoreRegex(
            r'Read timed out',
        )
        stdout_watcher.ignoreRegex(
            r'Error parsing status line',
        )
        stdout_watcher.ignoreRegex(
            r'WARNING Invalid content length: invalid literal for int'
        )
        stdout_watcher.ignoreRegex(
            r'encountered an error: zlib error: '
        )
        stdout_watcher.ignoreRegex(
            r'WARNING Discarding malformed URL '
        )

if __name__ == "__main__":
    Fuzzer().main()