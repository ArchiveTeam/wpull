import datetime
import gettext
import logging

import asyncio

from wpull.application.app import Application
from wpull.application.hook import HookableMixin
from wpull.application.plugin import PluginFunctions, hook_interface
from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.pipeline import ItemTask
import wpull.string
import wpull.url
import wpull.util
import wpull.warc
from wpull.stats import Statistics
from wpull.pipeline.app import AppSession
import wpull.application.hook
from wpull.application.hook import HookDisconnected


_logger = logging.getLogger(__name__)
_ = gettext.gettext


class BackgroundAsyncCleanupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        for server in session.async_servers:
            server.close()

        for task in session.background_async_tasks:
            yield from task


class AppStopTask(ItemTask[AppSession], HookableMixin):
    def __init__(self):
        super().__init__()
        self.hook_dispatcher.register(PluginFunctions.exit_status)

    @asyncio.coroutine
    def process(self, session: AppSession):
        statistics = session.factory['Statistics']
        app = session.factory['Application']
        self._update_exit_code_from_stats(statistics, app)

        try:
            new_exit_code = self.hook_dispatcher.call(PluginFunctions.exit_status, session, app.exit_code)
            app.exit_code = new_exit_code
        except HookDisconnected:
            pass

    @classmethod
    def _update_exit_code_from_stats(cls, statistics: Statistics,
                                     app: Application):
        '''Set the current exit code based on the Statistics.'''
        for error_type in statistics.errors:
            exit_code = app.ERROR_CODE_MAP.get(error_type)
            if exit_code:
                app.update_exit_code(exit_code)

    @staticmethod
    @hook_interface(PluginFunctions.exit_status)
    def plugin_exit_status(app_session: AppSession, exit_code: int) -> int:
        '''Return the program exit status code.

        Exit codes are values from :class:`errors.ExitStatus`.

        Args:
            exit_code: The exit code Wpull wants to return.

        Returns:
            int: The exit code that Wpull will return.
        '''
        return exit_code


class CookieJarTeardownTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        if 'CookieJarWrapper' in session.factory:
            session.factory['CookieJarWrapper'].close()
