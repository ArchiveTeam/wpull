'''Mock FTP servers.'''
import logging
import socket

import asyncio

from wpull.testing.async import AsyncTestCase


_logger = logging.getLogger(__name__)


class MockFTPServer(object):
    def __init__(self):
        pass

    @asyncio.coroutine
    def __call__(self, reader, writer):
        _logger.debug('New session')
        session = FTPSession(reader, writer)

        try:
            yield from session.process()
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
        self._current_username = None
        self._current_password = None
        # NOTE: Do not add any symlink directory traversal attacks since
        # unit tests will be testing symlink support!
        self.routes = {
            '/':
                ('dir',
                 'junk\nexample1\nexample2💎\nexample (copy).txt\nreadme.txt\n'.encode('utf8'),
                 ('drw-r--r-- 1 smaug smaug 0 Apr 01 00:00 junk\r\n'
                  'drw-r--r-- 1 smaug smaug 0 Apr 01 00:00 example1\r\n'
                  'drw-r--r-- 1 smaug smaug 0 Apr 01 00:00 example2💎\r\n'
                  '-rw-r--r-- 1 smaug smaug 42 Apr 01 00:00 example (copy).txt\r\n'
                  'lrwxrwxrwx 1 smaug smaug 4 Apr 01 00:00 readme.txt -> example (copy).txt\r\n'
                 ).encode('utf-8')),
            '/example (copy).txt':
                ('file',
                 'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8')),
            '/readme.txt':
                ('file',
                 'The real treasure is in Smaug’s heart 💗.\n'.encode('utf-8')),
            '/empty':
                ('dir', b'', b''),
            '/example1':
                ('dir', b'loopy', b'loopy'),
            '/example1/loopy':
                ('symlink', '/'),
            '/example2💎':
                ('dir', b'trash.txt',
                 ('02-09-2010  03:00PM                      13 trash.txt\r\n'
                 ).encode('utf-8'),
                 b'type=file; trash.txt\n'
                ),
            '/example2💎/trash.txt':
                ('file', b'hello dragon!'),
            '/hidden/sleep.txt':
                ('file', b'asdf'),
            '/hidden/invalid_chars':
                ('dir', b'wow\xf0\xff', b'wow\xf0\xff'),
        }
        self.command = None
        self.arg = None
        self.path = '/'
        self.evil_flags = set()
        self.restart_value = None

    @asyncio.coroutine
    def process(self):
        self.writer.write(b'220-Welcome to Smaug\'s FTP server\r\n')
        self.writer.write(b'220 Please upload your treasures now.\r\n')

        while True:
            yield from self.writer.drain()
            _logger.debug('Await command')
            line = yield from self.reader.readline()

            if line[-1:] != b'\n':
                _logger.debug('Connection closed')
                return

            try:
                command, arg = line.decode('utf-8', errors='replace').split(' ', 1)
            except ValueError:
                command = line.decode('utf-8', errors='replace').strip()
                arg = ''

            self.command = command.upper()
            self.arg = arg.rstrip()

            path = self.arg.rstrip('/') or '/'

            if not path.startswith('/'):
                self.path = self.path.rstrip('/') + '/' + path
            else:
                self.path = path

            info = self.routes.get(self.path)

            if info and info[0] == 'symlink':
                self.path = info[1]

            funcs = {
                'USER': self._cmd_user,
                'PASS': self._cmd_pass,
                'PASV': self._cmd_pasv,
                'NLST': self._cmd_nlst,
                'LIST': self._cmd_list,
                'MLSD': self._cmd_mlsd,
                'RETR': self._cmd_retr,
                'SIZE': self._cmd_size,
                'REST': self._cmd_rest,
                'CWD': self._cmd_cwd,
                'TYPE': self._cmd_type,
                'PWD': self._cmd_pwd,
                'EVIL_BAD_PASV_ADDR': self._cmd_evil_bad_pasv_addr,
            }
            func = funcs.get(self.command)

            _logger.debug('Command %s Arg %s Path %s', self.command, self.arg,
                          self.path)

            if not func:
                self.writer.write(b'500 Unknown command\r\n')
            else:
                if self.command not in ('USER', 'PASS') and \
                        not self._current_password:
                    self.writer.write(b'530 Login required\r\n')
                else:
                    yield from func()

    @asyncio.coroutine
    def _cmd_user(self):
        self._current_username = self.arg

        if self._current_username == 'no_password_required':
            self.writer.write(b'230 Log in OK\r\n')
            self._current_password = 'no_password_required'
        else:
            self.writer.write(b'331 Password required\r\n')

    @asyncio.coroutine
    def _cmd_pass(self):
        if self._current_username == 'anonymous':
            self.writer.write(b'230 Log in OK\r\n')
            self._current_password = self.arg
        elif self._current_username == 'smaug' and self.arg == 'gold1':
            self.writer.write(b'230 Welcome!\r\n')
            self._current_password = self.arg
        else:
            self.writer.write(b'530 Password incorrect\r\n')

    @asyncio.coroutine
    def _cmd_pasv(self):
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))

        def data_server_cb(data_reader, data_writer):
            self.data_reader = data_reader
            self.data_writer = data_writer

        self.data_server = yield from \
            asyncio.start_server(data_server_cb, sock=sock)
        port = sock.getsockname()[1]

        big_port_num = port >> 8
        small_port_num = port & 0xff

        if 'bad_pasv_addr' in self.evil_flags:
            self.writer.write(b'227 Now passive mode (127,0,0,WOW,SO,UNEXPECT)\r\n')
        else:
            self.writer.write('227 Now passive mode (127,0,0,1,{},{})\r\n'
                              .format(big_port_num, small_port_num)
                              .encode('utf-8'))

    @asyncio.coroutine
    def _wait_data_writer(self):
        for dummy in range(50):
            if not self.data_writer:
                yield from asyncio.sleep(0.1)
            else:
                return
        raise Exception('Time out')

    @asyncio.coroutine
    def _cmd_nlst(self):
        yield from self._wait_data_writer()

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
            return
        else:
            self.writer.write(b'125 Begin listings\r\n')

            info = self.routes.get(self.path)

            _logger.debug('Info: %s', info)

            if info and info[0] == 'dir':
                self.data_writer.write(info[1])

            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End listings\r\n')
            self.data_server.close()

    @asyncio.coroutine
    def _cmd_list(self):
        yield from self._wait_data_writer()

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        else:
            self.writer.write(b'125 Begin listings\r\n')

            info = self.routes.get(self.path)

            _logger.debug('Info: %s', info)

            if info and info[0] == 'dir':
                self.data_writer.write(info[2])

            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End listings\r\n')
            self.data_server.close()

    @asyncio.coroutine
    def _cmd_mlsd(self):
        yield from self._wait_data_writer()

        info = self.routes.get(self.path)

        if info and len(info) != 4:
            self.writer.write(b'500 What?\r\n')
            return

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        else:
            self.writer.write(b'125 Begin listings\r\n')

            info = self.routes.get(self.path)

            _logger.debug('Info: %s', info)

            if info and info[0] == 'dir':
                self.data_writer.write(info[3])

            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End listings\r\n')
            self.data_server.close()

    @asyncio.coroutine
    def _cmd_retr(self):
        yield from self._wait_data_writer()

        info = self.routes.get(self.path)

        if not self.data_writer:
            self.writer.write(b'227 Use PORT or PASV first\r\n')
        elif info and info[0] == 'file':
            self.writer.write(b'150 Begin data\r\n')

            if self.path == '/hidden/sleep.txt':
                yield from asyncio.sleep(2)

            self.data_writer.write(info[1][self.restart_value or 0:])
            self.restart_value = None
            self.data_writer.close()
            self.data_writer = None
            self.writer.write(b'226 End data\r\n')
            self.data_server.close()

            if self.path == '/example2💎/trash.txt':
                self.writer.close()
        else:
            self.writer.write(b'550 File error\r\n')

    @asyncio.coroutine
    def _cmd_size(self):
        info = self.routes.get(self.path)

        if info and info[0] == 'file' and self.path == '/example.txt':
            self.writer.write(b'213 ')
            self.writer.write(str(len(info[1])).encode('ascii'))
            self.writer.write(b'\r\n')
        elif info and info[0] == 'file' and self.path == '/example2💎/trash.txt':
            self.writer.write(b'213 3.14\r\n')
        else:
            self.writer.write(b'550 Unknown command\r\n')

    @asyncio.coroutine
    def _cmd_rest(self):
        try:
            self.restart_value = int(self.arg)

            if self.restart_value < 0 or self.restart_value == 99999:
                raise ValueError()

            self.writer.write(b'350 Restarting file\r\n')
        except ValueError:
            _logger.debug('Invalid restart value')
            self.restart_value = None
            self.writer.write(b'550 What?\r\n')

    @asyncio.coroutine
    def _cmd_cwd(self):
        if self.arg in ('example1', 'example2💎', '/'):
            self.writer.write(b'250 Changed directory\r\n')
        else:
            self.writer.write(b'550 Change directory error\r\n')

    @asyncio.coroutine
    def _cmd_type(self):
        if self.arg == 'I':
            self.writer.write(b'200 Now binary mode\r\n')
        else:
            self.writer.write(b'500 Unknown type\r\n')

    @asyncio.coroutine
    def _cmd_pwd(self):
        self.writer.write(b'257 /\r\n')

    @asyncio.coroutine
    def _cmd_evil_bad_pasv_addr(self):
        self.evil_flags.add('bad_pasv_addr')


class FTPTestCase(AsyncTestCase):
    def server_port(self):
        return self.sock.getsockname()[1]

    def setUp(self):
        AsyncTestCase.setUp(self)
        self.server = MockFTPServer()
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.server_handle = self.event_loop.run_until_complete(
            asyncio.start_server(self.server, sock=self.sock)
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
    handle = asyncio.get_event_loop().run_until_complete(
        asyncio.start_server(server, port=8020))
    asyncio.get_event_loop().run_forever()
