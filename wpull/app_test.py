# encoding=utf-8
import glob
from http import cookiejar
import re
from tempfile import TemporaryDirectory
import contextlib
import gzip
import hashlib
import logging
import os
import socket
import sys
import tempfile
import unittest

from tornado.testing import AsyncHTTPSTestCase
from trollius import From, Return
import tornado.testing
import trollius

from wpull.builder import Builder
from wpull.dns import Resolver
from wpull.errors import ExitStatus, SSLVerificationError
from wpull.http.web import WebSession
from wpull.options import AppArgumentParser
from wpull.testing.async import AsyncTestCase
from wpull.testing.badapp import BadAppTestCase
from wpull.testing.goodapp import GoodAppTestCase, GoodAppHTTPSTestCase
from wpull.url import URLInfo
from wpull.util import IS_PYPY
import wpull.testing.async
from wpull.testing.ftp import FTPTestCase


DEFAULT_TIMEOUT = 30


_logger = logging.getLogger(__name__)


class MockDNSResolver(Resolver):
    def __init__(self, *args, **kwargs):
        Resolver.__init__(self, *args, **kwargs)
        self.hosts_touched = set()

    @trollius.coroutine
    def resolve(self, host, port):
        self.hosts_touched.add(host)
        raise Return((socket.AF_INET, ('127.0.0.1', port)))


@contextlib.contextmanager
def cd_tempdir():
    original_dir = os.getcwd()
    with TemporaryDirectory() as temp_dir:
        try:
            os.chdir(temp_dir)
            yield temp_dir
        finally:
            os.chdir(original_dir)


class TestApp(GoodAppTestCase):
    def setUp(self):
        self._original_cookiejar_debug = cookiejar.debug
        cookiejar.debug = True
        super().setUp()
        self.original_loggers = list(logging.getLogger().handlers)

    def tearDown(self):
        GoodAppTestCase.tearDown(self)
        cookiejar.debug = self._original_cookiejar_debug

        for handler in list(logging.getLogger().handlers):
            if handler not in self.original_loggers:
                logging.getLogger().removeHandler(handler)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_args(self):
        arg_parser = AppArgumentParser(real_exit=False)
        self.assertRaises(ValueError, arg_parser.parse_args, [])

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_one_page(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/')])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
            self.assertTrue(os.path.exists('index.html'))

            response = yield From(tornado_future_adapter(self.http_client.fetch(self.get_url('/'))))

            with open('index.html', 'rb') as in_file:
                self.assertEqual(response.body, in_file.read())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        cookies = list(builder.factory['CookieJar'])
        _logger.debug('{0}'.format(cookies))
        self.assertEqual(1, len(cookies))
        self.assertEqual('hi', cookies[0].name)
        self.assertEqual('hello', cookies[0].value)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_big_payload(self):
        hash_obj = hashlib.sha1(b'foxfoxfox')
        payload_list = []

        for dummy in range(10000):
            data = hash_obj.digest()
            hash_obj.update(data)
            payload_list.append(data)

        data = hash_obj.digest()
        payload_list.append(data)
        expected_payload = b''.join(payload_list)

        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([self.get_url('/big_payload')])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
            self.assertTrue(os.path.exists('big_payload'))

            with open('big_payload', 'rb') as in_file:
                self.assertEqual(expected_payload, in_file.read())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_many_page_with_some_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/blog/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '-4',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(ExitStatus.server_error, exit_code)
        self.assertGreater(builder.factory['Statistics'].files, 1)
        self.assertGreater(builder.factory['Statistics'].duration, 3)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            '/',
            '--base', self.get_url('/').encode('utf-8'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--database', b'test.db',
            '--server-response',
            '--random-wait',
            b'--wait', b'0.1',
            '--protocol-directories',
            '--referer', 'http://test.test',
            '--accept-regex', r'.*',
            '--header', 'Hello: world!',
            '--exclude-domains', 'asdf.invalid',
            '--exclude-hostnames', 'qwerty.invalid,uiop.invalid',
            '--no-clobber',
            '--rotate-dns',
            '-4',
            '--concurrent', '2',
            '--no-check-certificate',
            '--ascii-print',
            '--progress', 'dot',
            '--secure-protocol', 'TLSv1',
            '--convert-links', '--backup-converted',
            '--accept', '*',
            '--restrict-file-names', 'windows,lower',
            '--quota', '10m',
            '--max-filename-length', '100',
            '--user-agent', 'ΑΒΓαβγ',
            '--remote-encoding', 'latin1',
            '--http-compression',
            '--bind-address', '127.0.0.1',
            '--html-parser', 'html5lib',
            '--link-extractors', 'html',
            '--page-requisites-level', '5',
            '--no-strong-crypto',
            '--no-skip-getaddrinfo',
            '--limit-rate', '1m',
        ])
        with cd_tempdir():
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            print(list(os.walk('.')))
            self.assertTrue(os.path.exists(
                'http/localhost+{0}/index.html'.format(self.get_http_port())
            ))
            self.assertTrue(os.path.exists(
                'http/localhost+{0}/index.html.orig'.format(
                    self.get_http_port())
            ))

        self.assertEqual(0, exit_code)
        self.assertEqual(builder.factory['Statistics'].files, 2)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_input_file_arg(self):
        arg_parser = AppArgumentParser(real_exit=False)
        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(self.get_url('/').encode('utf-8'))
            in_file.write(b'\n')
            in_file.write(self.get_url('/blog/?ðfßðfëéå').encode('utf-8'))
            in_file.flush()

            args = arg_parser.parse_args([
                '--input-file', in_file.name
            ])
            with cd_tempdir():
                builder = Builder(args, unit_test=True)
                app = builder.build()
                exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(builder.factory['Statistics'].files, 2)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_input_html_file_arg(self):
        arg_parser = AppArgumentParser(real_exit=False)
        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(b'<html><body><a href="')
            in_file.write(self.get_url('/').encode('utf-8'))
            in_file.write(b'">blah<a href="\n')
            in_file.write(self.get_url('/blog/?ðfßðfëéå').encode('utf-8'))
            in_file.write(b'">core</a>')
            in_file.flush()

            args = arg_parser.parse_args([
                '--input-file', in_file.name,
                '--force-html',
            ])
            with cd_tempdir():
                builder = Builder(args, unit_test=True)
                app = builder.build()
                exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(builder.factory['Statistics'].files, 2)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc_size(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--warc-file', 'test',
            '-4',
            '--no-robots',
            '--warc-max-size', '1k',
            '--warc-cdx'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertTrue(os.path.exists('test-00000.warc.gz'))
            self.assertTrue(os.path.exists('test-meta.warc.gz'))
            self.assertTrue(os.path.exists('test.cdx'))

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--recursive',
            '--page-requisites',
            '--warc-file', 'test',
            '-4',
            '--no-robots',
            '--no-warc-digests',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertTrue(os.path.exists('test.warc.gz'))

            with gzip.GzipFile('test.warc.gz') as in_file:
                data = in_file.read()
                self.assertIn(b'FINISHED', data)

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc_with_cdx(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-parent',
            '--warc-file', 'test',
            '-4',
            '--no-robots',
            '--warc-cdx',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_warc_dedup(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            with open('dedup.cdx', 'wb') as out_file:
                out_file.write(b' CDX a k u\n')
                out_file.write(
                    self.get_url('/static/my_file.txt').encode('ascii')
                )
                out_file.write(b' KQ4IUKATKL63FT5GMAE2YDRV3WERNL34')
                out_file.write(b' <under-the-deer>\n')

            args = arg_parser.parse_args([
                self.get_url('/static/my_file.txt'),
                '--no-parent',
                '--warc-file', 'test',
                '--no-warc-compression',
                '-4',
                '--no-robots',
                '--warc-dedup', 'dedup.cdx',
            ])

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            with open('test.warc', 'rb') as in_file:
                data = in_file.read()

                self.assertIn(b'KQ4IUKATKL63FT5GMAE2YDRV3WERNL34', data)
                self.assertIn(b'Type: revisit', data)
                self.assertIn(b'<under-the-deer>', data)

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_args_post_data(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/post/'),
            '--post-data', 'text=hi',
        ])
        with cd_tempdir():
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_sanity(self):
        arg_items = [
            ('--verbose', '--quiet'),
            ('--timestamp', '--no-clobber'),
            ('--inet4-only', '--inet6-only'),
            ('--warc-file=test', '--no-clobber'),
            ('--warc-file=test', '--timestamping'),
            ('--warc-file=test', '--continue'),
            ('--lua-script=blah.lua', '--python-script=blah.py'),
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
                arg_parser.parse_args([self.get_url('/')] + list(arg_item))
            except ValueError as error:
                self.assertEqual(2, error.args[0])
            else:
                self.assertTrue(False)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_python_script_api_2(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'testing', 'py_hook_script2.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            self.get_url('/some_page'),
            self.get_url('/mordor'),
            'localhost:1/wolf',
            '--python-script', filename,
            '--page-requisites',
            '--reject-regex', '/post/',
            '--wait', '12',
            '--retry-connrefused', '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
            print(list(os.walk('.')))

        self.assertEqual(42, exit_code)

        engine = builder.factory['Engine']
        self.assertEqual(2, engine.concurrent)

        stats = builder.factory['Statistics']

        self.assertEqual(3, stats.files)

        # duration should be virtually 0 but account for slowness on travis ci
        self.assertGreater(10.0, stats.duration)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_python_script_stop(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'testing', 'py_hook_script_stop.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--python-script', filename,
        ])
        with cd_tempdir():
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(1, exit_code)

    @unittest.skipIf(sys.version_info[0:2] == (3, 2),
                     'lua module not working in this python version')
    @unittest.skipIf(IS_PYPY, 'Not supported under PyPy')
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_lua_script_api_2(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'testing', 'lua_hook_script2.lua')
        args = arg_parser.parse_args([
            self.get_url('/'),
            self.get_url('/some_page'),
            self.get_url('/mordor'),
            'localhost:1/wolf',
            '--lua-script', filename,
            '--page-requisites',
            '--reject-regex', '/post/',
            '--wait', '12',
            '--retry-connrefused', '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
            print(list(os.walk('.')))

        self.assertEqual(42, exit_code)

        engine = builder.factory['Engine']
        self.assertEqual(2, engine.concurrent)

        stats = builder.factory['Statistics']

        self.assertEqual(3, stats.files)

        # duration should be virtually 0 but account for slowness on travis ci
        self.assertGreater(10.0, stats.duration)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_plugin_script(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(
            os.path.dirname(__file__), 'testing', 'plugin_script.py'
        )
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--plugin-script', filename,
            ])
        with cd_tempdir():
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(42, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_iri_handling(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/static/mojibake.html'),
            '-r',
            '--database', 'temp-unittest.db'
        ])
        with cd_tempdir():
            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            urls = tuple(url_record.url for url_record in
                         builder.factory['URLTable'].get_all())
            self.assertIn(
                self.get_url('/%E6%96%87%E5%AD%97%E5%8C%96%E3%81%91'),
                urls
            )

        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_cookie(self):
        arg_parser = AppArgumentParser()

        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(b'# Kittens\n')
            in_file.write(b'localhost.local')
            in_file.write(b'\tFALSE\t/\tFALSE\t\ttest\tno\n')
            in_file.flush()

            args = arg_parser.parse_args([
                self.get_url('/cookie'),
                '--load-cookies', in_file.name,
                '--tries', '1',
                '--save-cookies', 'wpull_test_cookies.txt',
                '--keep-session-cookies',
            ])
            builder = Builder(args, unit_test=True)

            with cd_tempdir():
                app = builder.build()
                exit_code = yield From(app.run())

                self.assertEqual(0, exit_code)
                self.assertEqual(1, builder.factory['Statistics'].files)

                cookies = list(builder.factory['CookieJar'])
                _logger.debug('{0}'.format(cookies))
                self.assertEqual(1, len(cookies))
                self.assertEqual('test', cookies[0].name)
                self.assertEqual('yes', cookies[0].value)

                with open('wpull_test_cookies.txt', 'rb') as saved_file:
                    cookie_data = saved_file.read()

                self.assertIn(b'test\tyes', cookie_data)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_diff_host(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/redirect?where=diff-host&port={0}'.format(
                self.get_http_port())),
            '--waitretry', '0'
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        resolver = builder.factory['Resolver']
        self.assertIn('somewhereelse.invalid', resolver.hosts_touched)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_diff_host_recursive(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/redirect?where=diff-host&port={0}'.format(
                self.get_http_port())),
            '--recursive',
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        resolver = builder.factory['Resolver']
        self.assertIn('somewhereelse.invalid', resolver.hosts_touched)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_span_hosts_allow_linked(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url(
                '/span_hosts?port={0}'.format(self.get_http_port())
            ),
            '--span-hosts-allow', 'linked-pages',
            '--no-robots',
            '--recursive',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

        resolver = builder.factory['Resolver']
        self.assertIn('linked.test', resolver.hosts_touched)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_redirect_span_hosts_page_requisites(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url(
                '/span_hosts?port={0}'.format(self.get_http_port())
            ),
            '--span-hosts-allow', 'page-requisites',
            '--no-robots',
            '--page-requisites',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

        resolver = builder.factory['Resolver']
        self.assertIn('pagereq.test', resolver.hosts_touched)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_strong_redirect(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/redirect?where=diff-host&port={0}'.format(
                self.get_http_port())),
            '--recursive',
            '--no-strong-redirects',
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

        resolver = builder.factory['Resolver']
        self.assertNotIn('somewhereelse.invalid', resolver.hosts_touched)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_immediate_robots_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--recursive',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            robots_txt_pool = builder.factory['RobotsTxtPool']
            robots_txt_pool.load_robots_txt(
                URLInfo.parse(self.get_url('/')),
                'User-Agent: *\nDisallow: *\n'
            )
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_immediate_robots_forbidden(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/forbidden'),
            '--recursive',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_immediate_robots_error(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            'http://127.0.0.1:1',
            self.get_url('/'),
            '--recursive',
            '--tries', '1',
            '--timeout', '1',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(4, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_quota(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/blog/'),
            '--recursive',
            '--quota', '1',
        ])

        with cd_tempdir():
            builder = Builder(args, unit_test=True)

            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_content_on_error(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/always_error'),
            '--content-on-error',
        ])

        with cd_tempdir():
            builder = Builder(args, unit_test=True)

            app = builder.build()
            exit_code = yield From(app.run())

            print(list(os.walk('.')))
            self.assertTrue(os.path.exists('always_error'))

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_sitemaps(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-robots',
            '--sitemaps',
            '--recursive',
        ])

        with cd_tempdir():
            builder = Builder(args, unit_test=True)

            app = builder.build()
            exit_code = yield From(app.run())

            print(list(os.walk('.')))
            self.assertTrue(os.path.exists(
                'localhost:{0}/static/my_file.txt'.format(
                    self.get_http_port())
            ))

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(4, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_sitemaps_and_no_parent(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/dir_or_file/'),
            '--no-robots',
            '--sitemaps',
            '--recursive',
            '--no-parent',
        ])

        with cd_tempdir():
            builder = Builder(args, unit_test=True)

            app = builder.build()
            exit_code = yield From(app.run())

            print(list(os.walk('.')))
            self.assertFalse(os.path.exists(
                'localhost:{0}/static/my_file.txt'.format(
                    self.get_http_port())
            ))

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_local_encoding(self):
        arg_parser = AppArgumentParser()

        with tempfile.NamedTemporaryFile() as in_file:
            in_file.write(self.get_url('/?qwerty').encode('utf-32-le'))
            in_file.write('\n'.encode('utf-32-le'))
            in_file.flush()

            opts = [
                self.get_url('/?asdf'),
                '--local-encoding', 'utf-32-le',
                '--input-file', in_file.name
            ]

            opts = [string.encode('utf-32-le') for string in opts]

            args = arg_parser.parse_args(opts)
            builder = Builder(args, unit_test=True)

            with cd_tempdir():
                app = builder.build()
                exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_iri(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-iri',
            '--no-robots'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_output_document(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            args = arg_parser.parse_args([
                self.get_url('/'),
                '--output-document', 'blah.dat'
            ])

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertTrue(os.path.exists('blah.dat'))

        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_misc_urls(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            args = arg_parser.parse_args([
                'http://[0:0:0:0:0:ffff:a00:0]/',
                '--tries', '1',
                '--timeout', '0.5',
                '-r',
            ])

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(4, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_database_uri(self):
        arg_parser = AppArgumentParser()

        with cd_tempdir():
            args = arg_parser.parse_args([
                self.get_url('/'),
                '--database-uri', 'sqlite:///test.db'
            ])

            builder = Builder(args, unit_test=True)
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_auth(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/basic_auth'),
            '--user', 'root',
            '--password', 'smaug',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic_auth_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/basic_auth'),
            '--user', 'root',
            '--password', 'toothless',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_page_requisite_level(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/infinite_iframe/'),
            '-r',
            '--page-requisites',
            '--page-requisites-level', '1',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

    # FIXME: not entirely working yet in JS scraper
    # it still grabs too much
    @unittest.skip('not entirely working yet in JS scraper')
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_link_type(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/always200/'),
            '-r',
            '--page-requisites',
            '--page-requisites-level', '2',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(4, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_escaped_fragment_input_url(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/escape_from_fragments/#!husky-cat'),
            '--escaped-fragment'
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)
            self.assertEqual(1, builder.factory['Statistics'].files)

            self.assertTrue(os.path.exists('index.html?_escaped_fragment_=husky-cat'))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_escaped_fragment_recursive(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/escape_from_fragments/'),
            '-r',
            '--escaped-fragment'
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_strip_session_id(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/forum/'),
            '-r',
            '--strip-session-id',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_referer_option(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/referrer/'),
            '-r',
            '--referer', 'http://left.shark/'
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(2, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_referer_option_negative(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/referrer/'),
            '-r',
            '--referer', 'http://superinformation.highway/',
            '--tries', '1',
            '--waitretry', '.1'
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @unittest.skip('not a good idea to test continuously on external servers')
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_youtube_dl(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            'https://www.youtube.com/watch?v=tPEE9ZwTmy0',
            '--warc-file', 'test',
            '--no-warc-compression',
            '--youtube-dl',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(0, exit_code)
            # TODO: proxy doesn't account for files yet
            # self.assertEqual(1, builder.factory['Statistics'].files)

            print(list(os.walk('.')))

            with open('test.warc', 'rb') as warc_file:
                data = warc_file.read()

                self.assertTrue(b'youtube-dl/' in data, 'include version')
                self.assertTrue(re.search(b'Fetched.*googlevideo\.com/videoplayback', data))

            video_files = tuple(glob.glob('*.mp4') + glob.glob('*.webm'))
            self.assertTrue(video_files)

            annotations = tuple(glob.glob('*.annotation*'))
            self.assertTrue(annotations)

            info_json = tuple(glob.glob('*.info.json'))
            self.assertTrue(info_json)

            # FIXME: version 2015.01.25 doesn't have thumbnail?
            # thumbnails = tuple(glob.glob('*.jpg'))
            # self.assertTrue(thumbnails)


class SimpleHandler(tornado.web.RequestHandler):
    def get(self):
        self.write(b'OK')


class TestAppHTTPS(AsyncTestCase, AsyncHTTPSTestCase):
    def get_new_ioloop(self):
        tornado.ioloop.IOLoop.configure(
            'wpull.testing.async.TornadoAsyncIOLoop',
            event_loop=self.event_loop)
        ioloop = tornado.ioloop.IOLoop()
        return ioloop

    def setUp(self):
        AsyncTestCase.setUp(self)
        AsyncHTTPSTestCase.setUp(self)

    def get_app(self):
        return tornado.web.Application([
            (r'/', SimpleHandler)
        ])

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_check_certificate(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(5, exit_code)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_https_only(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/?1'),
            self.get_url('/?2').replace('https://', 'http://'),
            '--https-only',
            '--no-robots',
            '--no-check-certificate',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)


    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_ssl_bad_certificate(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--no-robots',
            '--no-check-certificate',
            '--tries', '1'
            ])
        builder = Builder(args, unit_test=True)

        class MockWebSession(WebSession):
            @trollius.coroutine
            def fetch(self, file=None, callback=None):
                raise SSLVerificationError('A very bad certificate!')

        class MockWebClient(builder.factory.class_map['WebClient']):
            def session(self, request):
                return MockWebSession(self, request)

        with cd_tempdir():
            builder.factory.class_map['WebClient'] = MockWebClient

            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(7, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)


class PhantomJSMixin(object):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_app_phantomjs(self):
        arg_parser = AppArgumentParser()
        script_filename = os.path.join(os.path.dirname(__file__),
                                       'testing', 'boring_script.py')

        # Change localhost into something else to test proxy
        args = arg_parser.parse_args([
            self.get_url('/static/simple_javascript.html').replace('localhost', 'example.invalid'),
            '--warc-file', 'test',
            '--no-warc-compression',
            '-4',
            '--no-robots',
            '--phantomjs',
            '--phantomjs-exe', 'phantomjs',
            '--phantomjs-wait', '0.1',
            '--phantomjs-scroll', '2',
            '--header', 'accept-language: dragon',
            '--python-script', script_filename,
            '--no-check-certificate',
            ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertTrue(os.path.exists('test.warc'))
            self.assertTrue(
                os.path.exists('simple_javascript.html.snapshot.html')
            )
            self.assertTrue(
                os.path.exists('simple_javascript.html.snapshot.pdf')
            )

            with open('simple_javascript.html.snapshot.html', 'rb') as in_file:
                data = in_file.read()
                self.assertIn(b'Hello world!', data)

            with open('test.warc', 'rb') as in_file:
                data = in_file.read()

                self.assertIn(b'urn:X-wpull:snapshot?url=', data)
                self.assertIn(b'text/html', data)
                self.assertIn(b'application/pdf', data)
                self.assertIn(b'application/json', data)
                self.assertIn(b'"set_scroll_top"', data)
                try:
                    self.assertIn(b'Accept-Encoding: identity', data)
                except AssertionError:
                    # webkit treats localhost differently
                    self.assertNotIn(b'Accept-Encoding: gzip', data)
                self.assertIn(b'Accept-Language: dragon', data)

        self.assertEqual(0, exit_code)
        self.assertGreaterEqual(builder.factory['Statistics'].files, 1)

    # FIXME: for some reason, it never makes a connection to the proxy under
    # PyPy and Travis CI. eg: https://travis-ci.org/chfoo/wpull/jobs/49829901
    @unittest.skipIf(IS_PYPY, 'Broken under Travis CI')
    @wpull.testing.async.async_test(
        timeout=DEFAULT_TIMEOUT * 3 if IS_PYPY else DEFAULT_TIMEOUT
    )
    def test_app_phantomjs_scroll(self):
        arg_parser = AppArgumentParser()

        # Change localhost into something else to test proxy
        args = arg_parser.parse_args([
            self.get_url('/static/DEUUEAUGH.html').replace('localhost', 'example.invalid'),
            '-4',
            '--no-robots',
            '--phantomjs',
            '--phantomjs-wait', '0.4',
            '--phantomjs-scroll', '20',
            '--no-check-certificate',
            ])
        builder = Builder(args, unit_test=True)
        builder.factory.class_map['Resolver'] = MockDNSResolver

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            with open('DEUUEAUGH.html.snapshot.html', 'rb') as in_file:
                data = in_file.read()
                self.assertIn(b'Count: 10', data)

        self.assertEqual(0, exit_code)


class TestPhantomJS(GoodAppTestCase, PhantomJSMixin):
    pass


class TestPhantomJSHTTPS(GoodAppHTTPSTestCase, PhantomJSMixin):
    pass


class TestAppBad(BadAppTestCase):
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_cookie(self):
        import http.cookiejar
        http.cookiejar.debug = True
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/bad_cookie'),
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        cookies = list(builder.factory['CookieJar'])
        _logger.debug('{0}'.format(cookies))
        self.assertEqual(4, len(cookies))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_long_cookie(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/long_cookie'),
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())
        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

        cookies = list(builder.factory['CookieJar'])
        _logger.debug('{0}'.format(cookies))
        self.assertEqual(0, len(cookies))

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_non_http_redirect(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/non_http_redirect'),
            '--recursive',
            '--no-robots'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_bad_redirect(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/bad_redirect'),
            '--recursive',
            '--no-robots',
            '--waitretry', '0.1',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(7, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_ignore_length(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/underrun'),
            '--ignore-length',
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    # XXX: slow on pypy
    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT * 4)
    def test_bad_utf8(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/utf8_then_binary/doc.html'),
            self.get_url('/utf8_then_binary/doc.xml'),
            self.get_url('/utf8_then_binary/doc.css'),
            self.get_url('/utf8_then_binary/doc.js'),
            '--no-robots',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(4, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_no_content(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/no_content'),
            '--tries=1',
            ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)


class TestAppFTP(FTPTestCase):
    def setUp(self):
        super().setUp()
        self.original_loggers = list(logging.getLogger().handlers)

    def tearDown(self):
        FTPTestCase.tearDown(self)

        for handler in list(logging.getLogger().handlers):
            if handler not in self.original_loggers:
                logging.getLogger().removeHandler(handler)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_basic(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_login(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/example.txt'),
            '--user', 'smaug',
            '--password', 'gold1',
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(0, exit_code)
        self.assertEqual(1, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_login_fail(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/example.txt'),
            '--user', 'smaug',
            '--password', 'hunter2',
            '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

        self.assertEqual(8, exit_code)
        self.assertEqual(0, builder.factory['Statistics'].files)

    @wpull.testing.async.async_test(timeout=DEFAULT_TIMEOUT)
    def test_args(self):
        arg_parser = AppArgumentParser()
        args = arg_parser.parse_args([
            self.get_url('/'),
            self.get_url('/no_exist'),
            '-r',
            '--no-remove-listing',
            '--level', '1',  # TODO: handle symlink loops
            '--tries', '1',
            '--wait', '0',
            '--no-host-directories',
            '--warc-file', 'mywarc'
        ])
        builder = Builder(args, unit_test=True)

        with cd_tempdir():
            app = builder.build()
            exit_code = yield From(app.run())

            self.assertEqual(8, exit_code)
            self.assertEqual(5, builder.factory['Statistics'].files)

            print(os.listdir())

            self.assertTrue(os.path.exists('.listing'))
            self.assertTrue(os.path.exists('example.txt'))
            self.assertTrue(os.path.exists('example1/.listing'))
            self.assertTrue(os.path.exists('example2/.listing'))
            self.assertTrue(os.path.exists('mywarc.warc.gz'))

            with gzip.GzipFile('mywarc.warc.gz') as in_file:
                data = in_file.read()

                self.assertIn(b'FINISHED', data)
                self.assertIn('The real treasure is in Smaug’s heart 💗.\n'
                              .encode('utf-8'),
                              data)


@trollius.coroutine
def tornado_future_adapter(future):
    event = trollius.Event()

    future.add_done_callback(lambda dummy: event.set())

    yield From(event.wait())

    raise Return(future.result())
