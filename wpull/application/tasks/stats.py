import datetime
import gettext
import logging

import asyncio

from wpull.application.plugin import PluginFunctions, event_interface
from wpull.backport.logging import BraceMessage as __
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
from wpull.stats import Statistics
from wpull.application.hook import HookableMixin
import wpull.string
import wpull.application.hook

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class StatsStartTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        statistics = session.factory.new('Statistics',
                                         url_table=session.factory['URLTable'])
        statistics.quota = session.args.quota
        statistics.start()


class StatsStopTask(ItemTask[AppSession], HookableMixin):
    def __init__(self):
        super().__init__()
        self.event_dispatcher.register(PluginFunctions.finishing_statistics)

    @asyncio.coroutine
    def process(self, session: AppSession):
        statistics = session.factory['Statistics']
        statistics.stop()

        # TODO: human_format_speed arg
        self._print_stats(statistics)

        self.event_dispatcher.notify(PluginFunctions.finishing_statistics, session, statistics)

    @classmethod
    def _print_stats(cls, stats: Statistics, human_format_speed: bool=True):
        '''Log the final statistics to the user.'''
        time_length = datetime.timedelta(
            seconds=int(stats.stop_time - stats.start_time)
        )
        file_size = wpull.string.format_size(stats.size)

        if stats.bandwidth_meter.num_samples:
            speed = stats.bandwidth_meter.speed()

            if human_format_speed:
                speed_size_str = wpull.string.format_size(speed)
            else:
                speed_size_str = '{:.1f} b'.format(speed * 8)
        else:
            speed_size_str = _('-- B')

        _logger.info(_('FINISHED.'))
        _logger.info(__(
            _(
                'Duration: {preformatted_timedelta}. '
                'Speed: {preformatted_speed_size}/s.'
            ),
            preformatted_timedelta=time_length,
            preformatted_speed_size=speed_size_str,
        ))
        _logger.info(__(
            gettext.ngettext(
                'Downloaded: {num_files} file, {preformatted_file_size}.',
                'Downloaded: {num_files} files, {preformatted_file_size}.',
                stats.files
            ),
            num_files=stats.files,
            preformatted_file_size=file_size
        ))

        if stats.is_quota_exceeded:
            _logger.info(_('Download quota exceeded.'))

    @staticmethod
    @event_interface(PluginFunctions.finishing_statistics)
    def plugin_finishing_statistics(app_session: AppSession, statistics: Statistics):
        '''Callback containing final statistics.

        Args:
            start_time (float): timestamp when the engine started
            end_time (float): timestamp when the engine stopped
            num_urls (int): number of URLs downloaded
            bytes_downloaded (int): size of files downloaded in bytes
        '''
