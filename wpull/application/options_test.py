import unittest

from wpull.application.options import AppArgumentParser


class TestOptions(unittest.TestCase):
    def test_no_args(self):
        arg_parser = AppArgumentParser(real_exit=False)
        self.assertRaises(ValueError, arg_parser.parse_args, [])

    def test_app_sanity(self):
        arg_items = [
            ('--verbose', '--quiet'),
            ('--timestamp', '--no-clobber'),
            ('--inet4-only', '--inet6-only'),
            ('--warc-file=test', '--no-clobber'),
            ('--warc-file=test', '--timestamping'),
            ('--warc-file=test', '--continue'),
            ('--no-iri', '--local-encoding=shiftjis'),
            ('--no-iri', '--remote-encoding=shiftjis'),
        ]

        for arg_item in arg_items:
            def print_(message=None):
                print(message)

            def test_exit(status=0, message=None):
                raise ValueError(status, message)

            arg_parser = AppArgumentParser()
            arg_parser.exit = test_exit
            arg_parser.print_help = print_
            arg_parser.print_usage = print_

            try:
                print(arg_item)
                arg_parser.parse_args(['http://example.invalid'] + list(arg_item))
            except ValueError as error:
                self.assertEqual(2, error.args[0])
            else:
                self.assertTrue(False)
