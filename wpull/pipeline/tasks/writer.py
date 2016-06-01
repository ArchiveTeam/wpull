import gettext
import logging

import asyncio

from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
from wpull.writer import OverwriteFileWriter, IgnoreFileWriter, \
    TimestampingFileWriter, AntiClobberFileWriter, SingleDocumentWriter

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class FileWriterSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_file_writer(session)

    @classmethod
    def _build_file_writer(cls, session: AppSession):
        '''Create the File Writer.

        Returns:
            FileWriter: An instance of :class:`.writer.BaseFileWriter`.
        '''
        args = session.args

        if args.delete_after:
            return session.factory.new('FileWriter')  # is a NullWriter

        elif args.output_document:
            session.factory.class_map['FileWriter'] = SingleDocumentWriter
            return session.factory.new('FileWriter', args.output_document,
                                       headers_included=args.save_headers)

        use_dir = (len(args.urls) != 1 or args.page_requisites
                   or args.recursive)

        if args.use_directories == 'force':
            use_dir = True
        elif args.use_directories == 'no':
            use_dir = False

        os_type = 'windows' if 'windows' in args.restrict_file_names \
            else 'unix'
        ascii_only = 'ascii' in args.restrict_file_names
        no_control = 'nocontrol' not in args.restrict_file_names

        if 'lower' in args.restrict_file_names:
            case = 'lower'
        elif 'upper' in args.restrict_file_names:
            case = 'upper'
        else:
            case = None

        path_namer = session.factory.new(
            'PathNamer',
            args.directory_prefix,
            index=args.default_page,
            use_dir=use_dir,
            cut=args.cut_dirs,
            protocol=args.protocol_directories,
            hostname=args.host_directories,
            os_type=os_type,
            ascii_only=ascii_only,
            no_control=no_control,
            case=case,
            max_filename_length=args.max_filename_length,
        )

        if args.recursive or args.page_requisites or args.continue_download:
            if args.clobber_method == 'disable':
                file_class = OverwriteFileWriter
            else:
                file_class = IgnoreFileWriter
        elif args.timestamping:
            file_class = TimestampingFileWriter
        else:
            file_class = AntiClobberFileWriter

        session.factory.class_map['FileWriter'] = file_class

        return session.factory.new(
            'FileWriter',
            path_namer,
            file_continuing=args.continue_download,
            headers_included=args.save_headers,
            local_timestamping=args.use_server_timestamps,
            adjust_extension=args.adjust_extension,
            content_disposition=args.content_disposition,
            trust_server_names=args.trust_server_names,
        )
