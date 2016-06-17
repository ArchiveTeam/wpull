# encoding=utf-8
import os.path

from typing import cast, Optional

from wpull.application.hook import Actions
from wpull.application.plugin import WpullPlugin, hook, PluginFunctions, event
from wpull.network.dns import ResolveResult
from wpull.pipeline.app import AppSession
from wpull.pipeline.item import URLRecord
from wpull.pipeline.session import ItemSession
from wpull.stats import Statistics
from wpull.url import URLInfo
from wpull.protocol.http.request import Response as HTTPResponse


class Plugin(WpullPlugin):
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.injected_url_found = False
        self.got_redirected_page = False

    def activate(self):
        super().activate()
        self.app_session.factory['PipelineSeries'].concurrency = 2

    @hook(PluginFunctions.resolve_dns)
    def resolve_dns(self, host: str):
        print('resolve_dns', host)
        assert host == 'localhost'
        return '127.0.0.1'

    @hook(PluginFunctions.accept_url)
    def accept_url(self, item_session: ItemSession, verdict: bool, reasons: dict):
        url_info = item_session.request.url_info
        url_record = item_session.url_record
        print('accept_url', url_info)
        assert url_info

        if 'mailto:' in url_info.url:
            assert not verdict
            assert not reasons['filters']['SchemeFilter']
        else:
            assert url_info.path in (
                '/robots.txt', '/', '/post/',
                '/%95%B6%8E%9A%89%BB%82%AF/',
                '/static/style.css', '/wolf',
                '/some_page', '/some_page/',
                '/mordor',
                )
            assert reasons['filters']['SchemeFilter']

        for name, passed in reasons['filters'].items():
            assert name

        if url_info.path == '/':
            assert not url_record.inline_level
            assert verdict
        elif url_info.path == '/post/':
            assert not verdict
            verdict = True
        elif url_info.path == '/static/style.css':
            assert url_record.inline_level
        elif url_info.path == '/robots.txt':
            verdict = False

        return verdict

    @event(PluginFunctions.queued_url)
    def queued_url(self, url_info: URLInfo):
        print('queued_url', url_info)
        assert url_info.url

        self.counter += 1

        assert self.counter > 0

    @event(PluginFunctions.dequeued_url)
    def dequeued_url(self, url_info: URLInfo, record_info: URLRecord):
        print('dequeued_url', url_info)
        assert url_info.url
        assert record_info.url

        self.counter -= 1

        assert self.counter >= 0

    @hook(PluginFunctions.handle_pre_response)
    def handle_pre_response(self, item_session: ItemSession):
        if item_session.request.url_info.path == '/mordor':
            return Actions.FINISH

        return Actions.NORMAL

    @hook(PluginFunctions.handle_response)
    def handle_response(self, item_session: ItemSession):
        url_info = item_session.request.url_info
        print('handle_response', url_info)
        assert isinstance(item_session.response, HTTPResponse)

        response = cast(HTTPResponse, item_session.response)

        if url_info.path == '/':
            assert response.body.size
            assert response.status_code == 200
        elif url_info.path == '/post/':
            assert response.status_code == 200
            self.injected_url_found = True
            return Actions.FINISH
        elif url_info.path == '/some_page/':
            self.got_redirected_page = True

        return Actions.NORMAL

    @hook(PluginFunctions.handle_error)
    def handle_error(self, item_session: ItemSession, error: BaseException):
        print('handle_response', item_session.request.url, error)
        return Actions.NORMAL

    @event(PluginFunctions.get_urls)
    def get_urls(self, item_session: ItemSession):
        filename = item_session.response.body.name
        url_info = item_session.request.url_info
        print('get_urls', filename)
        assert filename
        assert os.path.isfile(filename)
        assert url_info.url

        if url_info.path == '/':
            item_session.add_child_url(
                'http://localhost:' + str(url_info.port) + '/post/',
                inline=True,
                post_data='text=hello',
                replace=True
            )
            item_session.add_child_url('..malformed')

    @hook(PluginFunctions.wait_time)
    def wait_time(self, seconds: float, item_session: ItemSession, error: Optional[Exception]=None):
        assert seconds >= 0
        return 0

    @event(PluginFunctions.finishing_statistics)
    def finish_statistics(self, app_session: AppSession, statistics: Statistics):
        print('finish_statistics', statistics.start_time)
        assert statistics.start_time
        assert statistics.stop_time

        print('queue counter', self.counter)
        assert self.counter == 0

    @hook(PluginFunctions.exit_status)
    def exit_status(self, app_session: AppSession, exit_code: int):
        assert exit_code == 4
        assert self.injected_url_found
        assert self.got_redirected_page
        print('exit_status', exit_code)
        return 42
