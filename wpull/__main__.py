# encoding=utf-8
import sys
import tornado.ioloop

from wpull.app import Builder
from wpull.options import AppArgumentParser


if __name__ == '__main__':
    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()
    io_loop = tornado.ioloop.IOLoop.instance()
    exit_code = Builder(args).build_and_run()
    sys.exit(exit_code)
    # TODO: catch SIGTERM and call stop()
