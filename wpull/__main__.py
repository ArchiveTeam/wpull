# encoding=utf-8
import os
import sys
import time

from wpull.builder import Builder
from wpull.options import AppArgumentParser


def main(exit=True):
    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()

    builder = Builder(args)
    builder.build()

    application = builder.factory['Application']
    application.setup_signal_handlers()
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
    elif os.environ.get('RUN_PDB'):
        import pdb

        def wrapper():
            main(exit=False)
            pdb.set_trace()

        pdb.runcall(wrapper)
    else:
        main()
