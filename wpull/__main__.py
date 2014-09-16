# encoding=utf-8
import os
import sys
import time

import tornado.platform.asyncio
import trollius

from wpull.builder import Builder
from wpull.options import AppArgumentParser


def main(exit=True, install_tornado_bridge=True, prefer_trollius=True):
    if prefer_trollius:
        try:
            import asyncio
        except ImportError:
            pass
        else:
            asyncio.set_event_loop_policy(trollius.get_event_loop_policy())

    if install_tornado_bridge:
        tornado.platform.asyncio.AsyncIOMainLoop().install()

    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()

    builder = Builder(args)
    builder.build()

    application = builder.factory['Application']
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


if __name__ == '__main__':
    if os.environ.get('RUN_PROFILE'):
        import cProfile
        cProfile.run('main()', 'stats-{0}.profile'.format(int(time.time())))
        # I suggest installing runsnakerun to view the profile file graphically
        # Or, for Python 3.4, use kcachegrind and pyprof2calltree
    elif os.environ.get('RUN_PDB'):
        import pdb

        def wrapper():
            main(exit=False)
            pdb.set_trace()

        pdb.runcall(wrapper)
    else:
        main()
