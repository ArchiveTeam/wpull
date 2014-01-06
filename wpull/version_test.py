# encoding=utf-8
from distutils.version import StrictVersion
import unittest

import wpull.version


class TestVersion(unittest.TestCase):
    def test_valid_version_str(self):
        StrictVersion(wpull.version.__version__)
