import asyncio
import functools

from typing import cast

from wpull.application.options import LOG_VERBOSE, LOG_DEBUG
from wpull.pipeline.app import AppSession, new_encoded_stream
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.progress import DotProgress, BarProgress, Progress, \
    ProtocolProgress
from wpull.protocol.http.client import Client as HTTPClient
from wpull.protocol.http.client import Session as HTTPSession
from wpull.protocol.ftp.client import Client as FTPClient
from wpull.protocol.ftp.client import Session as FTPSession


class ProgressSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        args = session.args

        if args.verbosity in (LOG_VERBOSE, LOG_DEBUG) and args.progress != 'none':
            stream = new_encoded_stream(args, session.factory.get_stderr())

            bar_style = args.progress == 'bar'

            if not stream.isatty():
                bar_style = False

            if bar_style == 'dot':
                session.factory.set('Progress', DotProgress)
            else:
                session.factory.set('Progress', BarProgress)

            progress = session.factory.new('Progress', stream=stream)

            self._attach_event_listeners(session, progress)
        else:
            session.factory.new('Progress')

    @classmethod
    def _attach_event_listeners(cls, session: AppSession, progress: ProtocolProgress):
        http_client = cast(HTTPClient, session.factory['HTTPClient'])
        http_client.event_dispatcher.add_listener(
            HTTPClient.ClientEvent.new_session,
            functools.partial(cls.http_session_callback, progress)
        )

        ftp_client = cast(FTPClient, session.factory['FTPClient'])
        ftp_client.event_dispatcher.add_listener(
            ftp_client.ClientEvent.new_session,
            functools.partial(cls.ftp_session_callback, progress)
        )

    @classmethod
    def http_session_callback(cls, progress: ProtocolProgress, http_session: HTTPSession):
        http_session.event_dispatcher.add_listener(
            HTTPSession.Event.begin_request,
            progress.update_from_begin_request)
        http_session.event_dispatcher.add_listener(
            HTTPSession.Event.begin_response,
            progress.update_from_begin_response)
        http_session.event_dispatcher.add_listener(
            HTTPSession.Event.end_response,
            progress.update_from_end_response)

    @classmethod
    def ftp_session_callback(cls, progress: ProtocolProgress, ftp_session: FTPSession):
        ftp_session.event_dispatcher.add_listener(
            FTPSession.Event.begin_control,
            progress.update_from_begin_request)
        ftp_session.event_dispatcher.add_listener(
            FTPSession.Event.begin_transfer,
            progress.update_from_begin_response)
        ftp_session.event_dispatcher.add_listener(
            FTPSession.Event.end_transfer,
            progress.update_from_end_response)
