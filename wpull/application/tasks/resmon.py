import gettext
import logging
import asyncio
import itertools
import tempfile

from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.app import AppSession
from wpull.pipeline.pipeline import ItemTask
import wpull.string
import wpull.application.hook
from wpull.pipeline.session import ItemSession
import wpull.resmon

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class ResmonSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        if not wpull.resmon.psutil:
            return

        paths = [session.args.directory_prefix, tempfile.gettempdir()]

        if session.args.warc_file:
            paths.append(session.args.warc_tempdir)

        session.factory.new(
            'ResourceMonitor',
            resource_paths=paths,
            min_memory=session.args.monitor_memory,
            min_disk=session.args.monitor_disk,
        )


class ResmonSleepTask(ItemTask[ItemSession]):
    @asyncio.coroutine
    def process(self, session: ItemSession):
        resource_monitor = session.app_session.factory.get('ResourceMonitor')

        if not resource_monitor:
            return

        resmon_semaphore = session.app_session.resource_monitor_semaphore

        if resmon_semaphore.locked():
            use_log = False
        else:
            use_log = True
            yield from resmon_semaphore.acquire()

        yield from self._polling_sleep(resource_monitor, log=use_log)

        if use_log:
            resmon_semaphore.release()

    @classmethod
    @asyncio.coroutine
    def _polling_sleep(cls, resource_monitor, log=False):
        for counter in itertools.count():
            resource_info = resource_monitor.check()

            if not resource_info:
                if log and counter:
                    _logger.info(_('Situation cleared.'))

                break

            if log and counter % 15 == 0:
                if resource_info.path:
                    _logger.warning(__(
                        _('Low disk space on {path} ({size} free).'),
                        path=resource_info.path,
                        size=wpull.string.format_size(resource_info.free)
                    ))
                else:
                    _logger.warning(__(
                        _('Low memory ({size} free).'),
                        size=wpull.string.format_size(resource_info.free)
                    ))

                _logger.warning(_('Waiting for operator to clear situation.'))

            yield from asyncio.sleep(60)
