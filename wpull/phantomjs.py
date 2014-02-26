# encoding=utf-8
'''PhantomJS wrapper.'''
import atexit
import contextlib
import json
import logging
import os.path
import time
import tornado.gen
import tornado.httpserver
import tornado.process
import tornado.testing
import tornado.web
import tornado.websocket
import toro
import uuid

import wpull.actor


_logger = logging.getLogger(__name__)

try:
    WebSocketClosedError = tornado.websocket.WebSocketClosedError
except AttributeError:
    WebSocketClosedError = AttributeError


class PhantomJSRPCError(Exception):
    '''Error during RPC call to PhantomJS.'''
    pass


class PhantomJSRemote(object):
    '''PhantomJS RPC wrapper.

    Args:
        exe_path (str): Path of the PhantomJS executable.

    This class automatically manages the life of the PhantomJS process. It
    will automatically terminate the process on interpreter shutdown.

    Attributes:
        page_event: An instance of :class:`.actor.Event` that is fired whenever
            a page event occurs. The argument passed to the listener is a
            RPC Info ``dict``.

    The messages passed are in the JSON format.
    '''
    def __init__(self, exe_path='phantomjs', extra_args=None,
    page_settings=None, default_headers=None):
        script_path = os.path.join(os.path.dirname(__file__), 'phantomjs.js')
        self._in_queue = toro.Queue()
        self._out_queue = toro.Queue()
        self.page_event = wpull.actor.Event()
        self._rpc_app = RPCApplication(self._out_queue, self._in_queue)
        self._http_server = tornado.httpserver.HTTPServer(self._rpc_app)
        http_socket, port = tornado.testing.bind_unused_port()
        self._subproc = tornado.process.Subprocess(
            [exe_path] + (extra_args or []) + [script_path, str(port)],
            stdout=tornado.process.Subprocess.STREAM,
        )
        self._rpc_reply_map = {}

        self._setup(http_socket, page_settings, default_headers)

    def _setup(self, http_socket, page_settings, default_headers):
        '''Set up the callbacks and loops.'''
        self._http_server.add_socket(http_socket)
        atexit.register(self._atexit_kill_subprocess)
        self._subproc.set_exit_callback(self._subprocess_exited_cb)
        tornado.ioloop.IOLoop.current().add_future(
            self._in_queue_loop(),
            lambda future: future.result()
        )
        tornado.ioloop.IOLoop.current().add_future(
            self._log_loop(),
            lambda future: future.result()
        )

        if page_settings:
            tornado.ioloop.IOLoop.current().add_future(
                self.call('setDefaultPageSettings', page_settings),
                lambda future: future.result()
            )

        if default_headers:
            tornado.ioloop.IOLoop.current().add_future(
                self.call('setDefaultPageHeaders', default_headers),
                lambda future: future.result()
            )

    def close(self):
        '''Terminate the PhantomJS process.'''
        if self._subproc.returncode is not None:
            return

        self._subproc.proc.terminate()

    @property
    def return_code(self):
        '''Return the exit code of the PhantomJS process.'''
        return self._subproc.returncode

    def _subprocess_exited_cb(self, exit_status):
        '''Callback when PhantomJS exits.'''
        _logger.debug('phantomjs exited with status {0}.'.format(exit_status))

    def _atexit_kill_subprocess(self):
        '''Terminate or kill the subprocess.

        This function is blocking.
        '''
        if self._subproc.returncode is not None:
            return

        self._subproc.proc.terminate()

        for dummy in range(10):
            if self._subproc.returncode is not None:
                return

            time.sleep(0.1)

        self._subproc.proc.kill()

    @tornado.gen.coroutine
    def _log_loop(self):
        '''Handle logging from PhantomJS output.'''
        while self._subproc.returncode is None:
            message = yield tornado.gen.Task(
                self._subproc.stdout.read_until, b'\n'
            )

            _logger.debug(
                'PhantomJS: {0}'.format(message.decode('utf-8').rstrip())
            )

    @tornado.gen.coroutine
    def _in_queue_loop(self):
        '''Handle messages populated in the queue.'''
        while self._subproc.returncode is None:
            message = yield self._in_queue.get()

            try:
                rpc_info = json.loads(message)
            except ValueError:
                _logger.exception('Error decoding message.')
            else:
                if 'event' in rpc_info:
                    self.page_event.fire(rpc_info)
                else:
                    self._process_rpc_result(rpc_info)

    @tornado.gen.coroutine
    def call(self, name, *args):
        '''Call a function.

        Args:
            name (str): The name of the function.
            args: Any arguments for the function.

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
        result = yield self._rpc_exec(rpc_info)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def set(self, name, value):
        '''Set a variable value.

        Args:
            name (str): The name of the variable.
            value: The value.

        Raises:
            PhantomJSRPCError
        '''
        rpc_info = {
            'action': 'set',
            'name': name,
            'value': value,
        }
        result = yield self._rpc_exec(rpc_info)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def eval(self, text):
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
        result = yield self._rpc_exec(rpc_info)
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def wait_page_event(self, event_name, deadline=None):
        '''Wait until given event occurs.

        Args:
            event_name (str): The event name.

        Returns:
            dict:
        '''
        async_result = toro.AsyncResult()

        def page_event_cb(rpc_info):
            if rpc_info['event'] == event_name:
                async_result.set(rpc_info)

        self.page_event.handle(page_event_cb)

        rpc_info = yield async_result.get(deadline)

        self.page_event.unhandle(page_event_cb)

        raise tornado.gen.Return(rpc_info)

    @tornado.gen.coroutine
    def _rpc_exec(self, rpc_info):
        '''Execute the RPC and return.

        Returns:
            something

        Raises:
            PhantomJSRPCError
        '''
        if 'id' not in rpc_info:
            rpc_info['id'] = uuid.uuid4().hex

        assert self._subproc.returncode is None

        rpc_call_info = yield self._put_rpc_info(rpc_info).get()

        if 'error' in rpc_call_info:
            raise PhantomJSRPCError(rpc_call_info['error']['stack'])
        elif 'result' in rpc_call_info:
            raise tornado.gen.Return(rpc_call_info['result'])

    def _put_rpc_info(self, rpc_info):
        '''Put the PPC info and AsyncResult into the mapping.

        Returns:
            AsyncResult: An instance of :class:`toro.AsyncResult`.
        '''
        async_result = toro.AsyncResult()
        self._rpc_reply_map[rpc_info['id']] = async_result

        self._out_queue.put(json.dumps(rpc_info))

        return async_result

    def _process_rpc_result(self, rpc_info):
        '''Match the reply and invoke the AsyncResult.'''
        answer_id = rpc_info['reply_id']
        async_result = self._rpc_reply_map[answer_id]
        async_result.set(rpc_info)


class RPCApplication(tornado.web.Application):
    '''RPC HTTP Application for PhantomJS.

    Args:
        out_queue: An instance of :class:`toro.Queue` that contains the
            messages to be send to PhantomJS.
        in_queue: An instance of :class:`toro.Queue` that contains the
            messages received from PhantomJS.
    '''
    def __init__(self, out_queue, in_queue):
        self.out_queue = out_queue
        self.in_queue = in_queue
        handlers = [
            (r'/', RPCHandler)
        ]
        super().__init__(handlers)


class RPCHandler(tornado.websocket.WebSocketHandler):
    '''WebSocket handler.'''
    def allow_draft76(self):
        return True

    def open(self):
        _logger.debug('Socket opened.')
        self.set_nodelay(True)

        tornado.ioloop.IOLoop.current().add_future(
            self._send_loop(),
            lambda future: future.result()
        )

    @tornado.gen.coroutine
    def on_message(self, message):
        _logger.debug('Received message {0}.'.format(message))

        yield self.application.in_queue.put(message)

    def on_close(self):
        _logger.debug('Socket closed.')

    @tornado.gen.coroutine
    def _send_loop(self):
        '''Handle sending the outgoing messages.'''
        out_queue = self.application.out_queue

        while self.ws_connection:
            message = yield out_queue.get()

            try:
                self.write_message(message)
            except WebSocketClosedError:
                _logger.exception('Error sending RPC message.')
                out_queue.put(message)


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
        if not self._remotes_ready:
            extra_args = [
                '--proxy={0}'.format(self._proxy_address)
            ]

            if self._extra_args:
                extra_args.extend(self._extra_args)

            _logger.debug(
                'Creating new remote with proxy {0}'.format(
                    self._proxy_address)
            )

            remote = PhantomJSRemote(
                self._exe_path,
                extra_args=extra_args,
                page_settings=self._page_settings,
                default_headers=self._default_headers,
            )

            tornado.ioloop.IOLoop.current().add_future(
                remote.set('rewriteEnabled', True),
                lambda future: future.result()
            )
        else:
            remote = self._remotes_ready.pop()

        self._remotes_busy.add(remote)

        assert remote.return_code is None

        try:
            yield remote
        finally:
            remote.page_event.clear()

            def put_back_remote(future):
                future.result()
                self._remotes_busy.remove(remote)
                self._remotes_ready.add(remote)

            tornado.ioloop.IOLoop.current().add_future(
                remote.call('resetPage'),
                put_back_remote
            )


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    phantomjs = PhantomJSRemote()

    tornado.ioloop.IOLoop.current().start()
