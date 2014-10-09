from tempfile import TemporaryDirectory
import os
import unittest


class BaseRecorderTest(unittest.TestCase):
    def setUp(self):
        unittest.TestCase.setUp(self)
        self.original_dir = os.getcwd()
        self.temp_dir = TemporaryDirectory()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()
        os.chdir(self.original_dir)
        unittest.TestCase.tearDown(self)
