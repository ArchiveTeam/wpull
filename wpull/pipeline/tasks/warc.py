import asyncio
import json

import sys

from wpull.pipeline.app import AppSession
from wpull.pipeline.pipeline import ItemTask
from wpull.warc.recorder import WARCRecorder, WARCRecorderParams
import wpull.driver.phantomjs
import wpull.processor.coprocessor.youtubedl


class WARCRecorderSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        args = session.args

        if not args.warc_file:
            return

        extra_fields = [
            ('robots', 'on' if args.robots else 'off'),
            ('wpull-arguments', str(args)),
            ('wpull-argv', json.dumps(sys.argv[1:])),
        ]

        for header_string in args.warc_header:
            name, value = header_string.split(':', 1)
            name = name.strip()
            value = value.strip()
            extra_fields.append((name, value))

        software_string = WARCRecorder.DEFAULT_SOFTWARE_STRING

        if args.phantomjs:
            software_string += ' PhantomJS/{0}'.format(
                wpull.driver.phantomjs.get_version(exe_path=args.phantomjs_exe)
            )

        if args.youtube_dl:
            software_string += ' youtube-dl/{0}'.format(
                wpull.processor.coprocessor.youtubedl.get_version(exe_path=args.youtube_dl_exe)
            )

        url_table = session.factory['URLTable'] if args.warc_dedup else None

        warc_recorder = session.factory.new(
            'WARCRecorder',
            args.warc_file,
            params=WARCRecorderParams(
                compress=not args.no_warc_compression,
                extra_fields=extra_fields,
                temp_dir=args.warc_tempdir,
                log=args.warc_log,
                appending=args.warc_append,
                digests=args.warc_digests,
                cdx=args.warc_cdx,
                max_size=args.warc_max_size,
                move_to=args.warc_move,
                url_table=url_table,
                software_string=software_string,
            ),
        )
        warc_recorder.listen_to_http_client(session.factory['HTTPClient'])
        warc_recorder.listen_to_ftp_client(session.factory['FTPClient'])


class WARCRecorderTeardownTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        warc_recorder = session.factory.get('WARCRecorder')

        if warc_recorder:
            warc_recorder.close()
