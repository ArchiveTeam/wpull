import asyncio

from typing import Optional

from wpull.application.factory import Factory
from wpull.pipeline.pipeline import ItemSource
import wpull.version
import wpull.util


class AppSession(object):
    def __init__(self, factory: Factory, args, stderr):
        self.default_user_agent = 'Wpull/{0} (gzip)'.format(
            wpull.version.__version__)
        self.factory = factory
        self.args = args
        self.stderr = stderr
        self.ca_certs_filename = None
        self.console_log_handler = None
        self.file_log_handler = None
        self.resource_monitor_semaphore = asyncio.BoundedSemaphore(1)
        self.ssl_context = None
        self.async_servers = []
        self.background_async_tasks = []
        self.proxy_server_port = None
        self.plugin_manager = None
        self.root_path = args.directory_prefix


class AppSource(ItemSource[AppSession]):
    def __init__(self, session: AppSession):
        self._source = session

    @asyncio.coroutine
    def get_item(self) -> Optional[AppSession]:
        item = self._source
        self._source = None
        return item


def new_encoded_stream(args, stream):
    '''Return a stream writer.'''
    if args.ascii_print:
        return wpull.util.ASCIIStreamWriter(stream)
    else:
        return stream
