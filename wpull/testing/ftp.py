'''Mock FTP servers.'''
import logging
import socket

from trollius import From, Return
import trollius

from wpull.testing.async import AsyncTestCase


_logger = logging.getLogger(__name__)


class MockFTPServer(object):
    def __init__(self):
        pass

    @trollius.coroutine
    def __call__(self, reader, writer):
        _logger.debug('New session')
        session = FTPSession(reader, writer)

        try:
            yield From(session.process())
        except Exception:
            _logger.exception('Server error')
            writer.close()
        else:
            writer.close()


class FTPSession(object):
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self.data_reader = None
        self.data_writer = None

    @trollius.coroutine
    def process(self):
        self.writer.write(b'220-Welcome to Smaug\'s FTP server\r\n')
        self.writer.write(b'220 Please upload your treasures now.\r\n')

        while True:
            yield From(self.writer.drain())
            _logger.debug('Await command')
            line = yield From(self.reader.readline())

            if line[-1:] != b'\n':
                _logger.debug('Connection closed')
                return

            try:
                command, arg = line.decode('latin-1').split(' ', 1)
            except ValueError:
                command = line.decode('latin-1').strip()
                arg = ''

            self.command = command.upper()
            self.arg = arg.rstrip()

            funcs = {
                'USER': self._cmd_user,
                'PASS': self._cmd_pass,
                'PASV': self._cmd_pasv,
                'NLST': self._cmd_nlst,
                'LIST': self._cmd_list,
                'RETR': self._cmd_retr,
                'CWD': self._cmd_cwd,
                'TYPE': self._cmd_type,
                'PWD': self._cmd_pwd,
            }
            func = funcs.get(self.command)

            _logger.debug('Command %s Arg %s', self.command, self.arg)

            if not func:
                self.writer.write(b'500 Unknown command\r\n')
            else:
                yield From(func())

    @trollius.coroutine
    def _cmd_user(self):
        self.writer.write(b'331 Password required\r\n')

    @trollius.coroutine
    def _cmd_pass(self):
        self.writer.write(b'230 Log in OK\r\n')

    @trollius.coroutine
    def _cmd_pasv(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))

        def data_server_cb(data_reader, data_writer):
            self.data_reader = data_reader
            self.data_writer = data_writer

        self.data_server = yield From(
            trollius.start_server(data_server_cb, sock=sock))
        port = sock.getsockname()[1]

        big_port_num = port >> 8
        small_port_num = port & 0xff
        self.writer.write('227 Now passive mode (127,0,0,1,{},{})\r\n'
                          .format(big_port_num, small_port_num)
                          .encode('latin-1'))

    @trollius.coroutine
    def _wait_data_writer(self):
        for dummy in range(50):
            if not self.data_writer:
                yield From(trollius.sleep(0.1))
            else:
                return
        raise Exception('Time out')

    @trollius.coroutine
    def _cmd_nlst(self):
        yield From(self._wait_data_writer())

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        else:
            self.writer.write(b'150 Begin listings\r\n')
            self.data_writer.write(b'example1\r\n')
            self.data_writer.write(b'example2\r\n')
            self.data_writer.write(b'example.txt\r\n')
            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End listings\r\n')
            self.data_server.close()

    @trollius.coroutine
    def _cmd_list(self):
        yield From(self._wait_data_writer())

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        else:
            self.writer.write(b'150 Begin listings\r\n')
            self.data_writer.write(b'drw-r--r-- 1 smaug smaug 0 Apr 01 00:00 example1\r\n')
            self.data_writer.write(b'drw-r--r-- 1 smaug smaug 0 Apr 01 00:00 example2\r\n')
            self.data_writer.write(b'-rw-r--r-- 1 smaug smaug 42 Apr 01 00:00 example.txt\r\n')
            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End listings\r\n')
            self.data_server.close()

    @trollius.coroutine
    def _cmd_retr(self):
        yield From(self._wait_data_writer())

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        elif self.arg.lstrip('/') == 'example.txt':
            self.writer.write(b'150 Begin data\r\n')
            self.data_writer.write(
                'The real treasure is in Smaug’s heart 💗.\n'
                .encode('utf-8'))
            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End data\r\n')
            self.data_server.close()
        else:
            self.writer.write(b'550 File error\r\n')

    @trollius.coroutine
    def _cmd_cwd(self):
        if self.arg in ('example1', 'example2', '/'):
            self.writer.write(b'250 Changed directory\r\n')
        else:
            self.writer.write(b'550 Change directory error\r\n')

    @trollius.coroutine
    def _cmd_type(self):
        if self.arg == 'I':
            self.writer.write(b'200 Now binary mode\r\n')
        else:
            self.writer.write(b'500 Unknown type\r\n')

    @trollius.coroutine
    def _cmd_pwd(self):
        self.writer.write(b'257 /\r\n')


class FTPTestCase(AsyncTestCase):
    def server_port(self):
        return self.sock.getsockname()[1]

    def setUp(self):
        AsyncTestCase.setUp(self)
        self.server = MockFTPServer()
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.server_handle = self.event_loop.run_until_complete(
            trollius.start_server(self.server, sock=self.sock)
        )

    def tearDown(self):
        self.server_handle.close()
        AsyncTestCase.tearDown(self)

    def get_url(self, path, username='', password=''):
        if username or password:
            return 'ftp://{username}@{password}:127.0.0.1:{port}{path}' \
                .format(path=path, port=self.server_port(),
                        username=username, password=password
                        )
        else:
            return 'ftp://127.0.0.1:{port}{path}'.format(
                path=path, port=self.server_port())


if __name__ == '__main__':
    server = MockFTPServer()
    handle = trollius.get_event_loop().run_until_complete(
        trollius.start_server(server, port=8020))
    trollius.get_event_loop().run_forever()
