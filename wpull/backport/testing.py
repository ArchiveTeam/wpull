# encoding=utf-8
import sys


# Snipped from tornado
if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest

__all__ = ['unittest']
