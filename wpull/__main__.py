import sys
import tornado.ioloop

from wpull.app import AppArgumentParser, build_engine


if __name__ == '__main__':
    arg_parser = AppArgumentParser()
    args = arg_parser.parse_args()
    io_loop = tornado.ioloop.IOLoop.instance()
    engine = build_engine(args)
    exit_code = io_loop.run_sync(engine)
    sys.exit(exit_code)
