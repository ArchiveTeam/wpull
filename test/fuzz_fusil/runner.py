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
import os.path
import random


class FuzzedHttpServer(HttpServer):
    def __init__(self, *args, **kwargs):
        random.seed(1)
        HttpServer.__init__(self, *args, **kwargs)
        self._config = MangleConfig(min_op=0, max_op=100)

    def serveData(self, client, code, code_text, data=None,
    content_type="text/html"):
        if data:
            data_len = len(data)
        else:
            data_len = 0
        http_headers = [
            ("Server", "Fusil"),
            ("Pragma", "no-cache"),
            ("Content-Type", content_type),
            ("Content-Length", str(data_len)),
        ]
        try:
            header = "HTTP/%s %s %s\r\n" % (self.http_version, code, code_text)
            for key, value in http_headers:
                header += "%s: %s\r\n" % (key, value)
            header += "\r\n"

            choice = random.randint(0, 2)
            self.logger.info('mangle choice: ' + str(choice), self)

            if choice == 1:
                header = self.mangle_data(header)
            elif data and choice == 2:
                data = self.mangle_data(data)

            if data:
                data = header + data
            else:
                data = header
            client.sendBytes(data)
            client.close()
        except ServerClientDisconnect:
            self.clientDisconnection(client)

    def mangle_data(self, data):
        mangler = Mangle(self._config, bytearray(data))
        mangler.run()

        self.logger.info(
            'Mangled data: ' + repr(mangler.data),
            self
        )

        return mangler.data


class Fuzzer(Application):
    def setupProject(self):
        self.project.debugger.enabled = False
        FuzzedHttpServer(self.project, 8898)

        process = ProjectProcess(
            self.project,
            ['python3', '-m', 'wpull',
                '127.0.0.1:8898',
                '--timeout', '2.0',
                '--tries', '1',
            ],
        )

        process.max_memory = 500000000

        process.env.set(
            'PYTHONPATH',
            os.path.join(
                os.path.abspath(os.path.dirname(__file__)), '..', '..')
        )
        WatchProcess(process)
        WatchStdout(process)


if __name__ == "__main__":
    Fuzzer().main()
