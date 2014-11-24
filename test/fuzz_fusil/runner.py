'''Fuzz tester.

This script to be run under Python 2.

Install dependencies via pip::

    pip install fusil python-ptrace
'''
from fusil.application import Application
from fusil.mangle import Mangle, MangleConfig
from fusil.network.http_server import HttpServer
from fusil.network.server_client import ServerClientDisconnect
from fusil.process.create import ProjectProcess
from fusil.process.stdout import WatchStdout
from fusil.process.watch import WatchProcess
import gzip
import os.path
import random
import sys
import socket


if sys.version_info[0] == 2:
    from cStringIO import StringIO as BytesIO
else:
    from io import BytesIO


class FuzzedHttpServer(HttpServer):
    SAMPLE_FILENAMES = (
        'krokozyabry.css',
        'soup.html',
        'mojibake.html',
        'styles.css',
        'krokozyabry.html',
        'webtv.net_tvfoutreach_cocountdownto666.html',
        'many_urls.html',
        'xkcd_1.html',
        'mojibake.css',
    )

    def __init__(self, *args, **kwargs):
        HttpServer.__init__(self, *args, **kwargs)
        self._config_light = MangleConfig(min_op=0, max_op=50)
        self._config_heavy = MangleConfig(min_op=0, max_op=500)

        self._data_samples = []

        for filename in self.SAMPLE_FILENAMES:
            path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '../', '../', 'wpull', 'testing', 'samples',
                filename
            )

            with open(path, 'rb') as in_file:
                self._data_samples.append(in_file.read())

        self._data_samples.append(
            "<html><body><p>Hello World!</p></body></html>")

    def serveRequest(self, client, request):
        url = request.uri[1:]
        if not url:
            url = "index.html"

        choice = random.randint(0, 1)

        self.logger.info('request choice: ' + str(choice), self)

        if choice == 1:
            self.serveData(
                client, 200, "OK", random.choice(self._data_samples))
        else:
            self.error404(client, url)

    def serveData(self, client, code, code_text, data=None,
    content_type="text/html"):
        data_choice = random.random()
        header_choice = random.random()
        http_headers = []

        if random.random() < 0.2:
            new_content_type = random.choice(
                ['text/html', 'image/png', 'text/css'])
            self.logger.info(
                'Mangle content_type {0} -> {1}'.format(
                    content_type, new_content_type),
                self
            )
            content_type = new_content_type

        if data and data_choice < 0.5:
            self.logger.info('Mangle content: YES', self)
            data = self.mangle_data(data, self._config_heavy)

        if random.random() < 0.2:
            self.logger.info('Mangle gzip: YES', self)

            datafile = BytesIO()

            with gzip.GzipFile(fileobj=datafile, mode='wb') as gzip_file:
                gzip_file.write(bytes(data))

            data = self.mangle_data(datafile.getvalue(), self._config_light)

            http_headers.append(('Content-Encoding', 'gzip'))

        if data:
            data_len = len(data)
        else:
            data_len = 0

        http_headers.extend([
            ("Server", "Fusil"),
            ("Pragma", "no-cache"),
            ("Content-Type", content_type),
            ("Content-Length", str(data_len)),
        ])

        try:
            header = "HTTP/%s %s %s\r\n" % (self.http_version, code, code_text)
            for key, value in http_headers:
                header += "%s: %s\r\n" % (key, value)
            header += "\r\n"

            if header_choice < 0.3:
                self.logger.info('Mangle header: YES', self)
                header = self.mangle_data(header, self._config_light)

            if data:
                data = header + data
            else:
                data = header
            client.sendBytes(data)
            client.close()
        except (ServerClientDisconnect, socket.error):
            self.clientDisconnection(client)

    def mangle_data(self, data, config):
        mangler = Mangle(config, bytearray(data))
        mangler.run()

        self.logger.info(
            'Mangled data: ' + repr(mangler.data),
            self
        )

        return mangler.data


class Fuzzer(Application):
    def setupProject(self):
        self.project.debugger.enabled = False
        self.config.process_max_user_process = 50

        FuzzedHttpServer(self.project, 8898)

        process = ProjectProcess(
            self.project,
            ['python3', '-m', 'wpull',
                '127.0.0.1:8898',
                '--timeout', '2.0',
                '--tries', '1',
            ],
        )

        process.env.set(
            'PYTHONPATH',
            os.path.join(
                os.path.abspath(os.path.dirname(__file__)), '..', '..')
        )

        WatchProcess(process, exitcode_score=0.45)
        stdout_watcher = WatchStdout(process)
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

if __name__ == "__main__":
    random.seed(1)
    Fuzzer().main()
