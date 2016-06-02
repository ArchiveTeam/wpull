import sys
import tornado.platform.asyncio

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser


def main(exit=True, install_tornado_bridge=True, use_signals=True):
    if install_tornado_bridge:
        tornado.platform.asyncio.AsyncIOMainLoop().install()

    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()

    builder = Builder(args)
    application = builder.build()

    if use_signals:
        application.setup_signal_handlers()

    if args.debug_manhole:
        import manhole
        import wpull
        wpull.wpull_builder = builder
        manhole.install()

    exit_code = application.run_sync()

    if exit:
        sys.exit(exit_code)
    else:
        return exit_code
