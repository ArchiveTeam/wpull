import os

from wpull.application.builder import Builder
from wpull.application.options import AppArgumentParser
from wpull.testing.integration.base import HTTPGoodAppTestCase
import wpull.testing.async


class TestScriptGoodApp(HTTPGoodAppTestCase):
    @wpull.testing.async.async_test()
    def test_app_empty_plugin_script(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'sample_user_scripts', 'boring.plugin.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--plugin-script', filename,
        ])
        builder = Builder(args, unit_test=True)
        app = builder.build()
        exit_code = yield from app.run()

        self.assertEqual(0, exit_code)

    @wpull.testing.async.async_test()
    def test_app_python_plugin_script(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'sample_user_scripts', 'extensive.plugin.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            self.get_url('/some_page'),
            self.get_url('/mordor'),
            'localhost:1/wolf',
            '--plugin-script', filename,
            '--page-requisites',
            '--reject-regex', '/post/',
            '--wait', '12',
            '--retry-connrefused', '--tries', '1'
        ])
        builder = Builder(args, unit_test=True)
    
        app = builder.build()
        exit_code = yield from app.run()
        print(list(os.walk('.')))
    
        self.assertEqual(42, exit_code)
    
        engine = builder.factory['PipelineSeries']
        self.assertEqual(2, engine.concurrency)
    
        stats = builder.factory['Statistics']
    
        self.assertEqual(3, stats.files)
    
        # duration should be virtually 0 but account for slowness on travis ci
        self.assertGreater(10.0, stats.duration)
    
    @wpull.testing.async.async_test()
    def test_app_python_script_stop(self):
        arg_parser = AppArgumentParser()
        filename = os.path.join(os.path.dirname(__file__),
                                'sample_user_scripts', 'stopper.plugin.py')
        args = arg_parser.parse_args([
            self.get_url('/'),
            '--plugin-script', filename,
        ])
        builder = Builder(args, unit_test=True)
        app = builder.build()
        exit_code = yield from app.run()
    
        self.assertEqual(1, exit_code)
