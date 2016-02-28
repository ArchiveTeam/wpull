import asyncio
import datetime
import gettext
import logging

from wpull.backport.logging import BraceMessage as __
from wpull.application.app import Application
from wpull.pipeline.pipeline import ItemTask
import wpull.string
from wpull.stats import Statistics

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class AppStartTask(ItemTask[Application]):
    @asyncio.coroutine
    def process(self, app: Application):
        statistics = app.builder.factory['Statistics']
        statistics.start()


class AppEndTask(ItemTask[Application]):
    @asyncio.coroutine
    def process(self, app: Application):
        statistics = app.builder.factory['Statistics']
        statistics.stop()

        # TODO: human_format_speed arg
        self._print_stats(statistics)

        # try:
        #     self.call_hook(
        #         'finishing_statistics',
        #         self._statistics.start_time, self._statistics.stop_time,
        #         self._statistics.files, self._statistics.size
        #     )
        # except HookDisconnected:
        #     pass

        self._update_exit_code_from_stats(statistics, app)

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

    @classmethod
    def _update_exit_code_from_stats(cls, statistics: Statistics,
                                      app: Application):
        '''Set the current exit code based on the Statistics.'''
        for error_type in statistics.errors:
            exit_code = app.ERROR_CODE_MAP.get(error_type)
            if exit_code:
                app.update_exit_code(exit_code)


    # TODO: implement these from the Application class
    # def _close(self):
    #     '''Perform clean up actions.'''
    #     self._builder.factory['WebProcessor'].close()
    #     self._builder.factory['URLTable'].close()

    # def add_server_task(self, task):
    #     '''Add a server task.'''
    #     self._server_tasks.append(task)
    #
    # @asyncio.coroutine
    # def _start_servers(self):
    #     '''Start servers.
    #
    #     Coroutine.
    #     '''
    #     for task in self._server_tasks:
    #         _logger.debug(__('Starting task {}', task))
    #         server = yield from task
    #         self._servers.append(server)
    #
    # def _close_servers(self):
    #     '''Close and wait for servers to close.
    #
    #     Coroutine.
    #     '''
    #     for server in self._servers:
    #         _logger.debug(__('Closing server {}', server))
    #         server.close()
    #         yield from server.wait_closed()
