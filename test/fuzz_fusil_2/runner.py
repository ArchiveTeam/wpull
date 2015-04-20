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


class WatchProcessSpecificStatusCode(WatchProcess):
    def computeScore(self, status):
        if status in (4, 6, 7, 8):
            print('Change status', status, 'to 0.')
            status = 0

        return WatchProcess.computeScore(self, status)


class Fuzzer(Application):
    def setupProject(self):
        self.project.debugger.enabled = False
        self.config.use_cpu_probe = False
        self.config.process_max_user_process = 50

        port = 8848
        seed = random.randint(0, 60000)
        timeout = 60 * 60

        server_process = ProjectProcess(
            self.project,
            [
                'python3', '-m', 'huhhttp',
                '--port', str(port),
                '--seed', str(seed),
                '--fuzz-period', '500',
                '--restart-interval', '250',
            ],
            timeout=timeout
        )
        WatchProcess(server_process)

        process = ProjectProcess(
            self.project,
            [
                'python3', '-X', 'faulthandler', '-m', 'wpull',
                '127.0.0.1:{0}'.format(port),
                '--timeout', '5',
                '--warc-file', 'fusil-test',
                '-r',
                '--debug',
                '--page-requisites',
                '--delete-after',
                '--tries', '2',
                '--retry-connrefused',
                '--database', 'wpull.db',
                '--span-hosts-allow', 'page-requisites,linked-pages',
                '--no-check-certificate',
                '--concurrent', str(random.randint(1, 10)),
            ],
            timeout=timeout
        )

        process.env.set(
            'PYTHONPATH',
            os.path.join(
                os.path.abspath(os.path.dirname(__file__)), '..', '..')
            )
        process.env.set('OBJGRAPH_DEBUG', '1')
        process.env.set('FILE_LEAK_DEBUG', '1')

        WatchProcessSpecificStatusCode(process)
        stdout_watcher = WatchStdout(process)
        stdout_watcher.max_nb_line = None
        stdout_watcher.ignoreRegex(
            r'WARNING Invalid content length: invalid literal for int'
        )
        stdout_watcher.ignoreRegex(
            r'WARNING Unable to parse URL '
        )
        stdout_watcher.ignoreRegex(
            r'WARNING Failed to read document at '
        )
        stdout_watcher.ignoreRegex(
            r'WARNING Content overrun'
        )
        stdout_watcher.ignoreRegex(
            r'ERROR Fetching '
        )
        stdout_watcher.ignoreRegex(
            r'DEBUG '
        )
        stdout_watcher.ignoreRegex(
            r'INFO Fetch(ed|ing) '
        )
        stdout_watcher.ignoreRegex(
            r'lsof: WARNING: '
        )

if __name__ == "__main__":
    Fuzzer().main()
