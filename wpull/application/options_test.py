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

    def test_comma_list_args(self):
        arg_item_list = [
            '--accept', '--reject',
            '--domains', '--exclude-domains',
            '--hostnames', '--exclude-hostnames',
            '--follow-tags', '--ignore-tags',
            '--include-directories', '--exclude-directories',
            '--proxy-domains', '--proxy-exclude-domains',
            '--proxy-hostnames', '--proxy-exclude-hostnames',
            ]
        arg_dest_list = [
            'accept', 'reject',
            'domains', 'exclude_domains',
            'hostnames', 'exclude_hostnames',
            'follow_tags', 'ignore_tags',
            'include_directories', 'exclude_directories',
            'proxy_domains', 'proxy_exclude_domains',
            'proxy_hostnames', 'proxy_exclude_hostnames',
            ]

        cli_input = 'item1,item2,item3'
        expected_value = ['item1', 'item2', 'item3']

        for arg_item, arg_dest in zip(arg_item_list, arg_dest_list):
            arg_parser = AppArgumentParser()

            args = arg_parser.parse_args(['http://example.invalid'] + [arg_item, cli_input])
            self.assertEqual(expected_value, vars(args)[arg_dest])
