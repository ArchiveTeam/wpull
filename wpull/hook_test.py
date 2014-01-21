# encoding=utf-8
import os.path
import sys

from wpull.backport.testing import unittest
from wpull.hook import to_lua_string, to_lua_type


class TestHook(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0:2] == (3, 2),
        'lua module not working in this python version')
    def test_lua_type_sanity(self):
        import lua

        test_filename = os.path.join(os.path.dirname(__file__),
            'testing', 'type_test.lua')

        lua_globals = lua.globals()
        lua_globals.text1 = to_lua_string('hi')
        lua_globals.text2 = to_lua_string('hé')
        lua_globals.text3 = to_lua_string('狗')
        lua_globals.num1 = to_lua_type(42)

        with open(test_filename, 'rb') as in_file:
            lua.execute(in_file.read())

        self.assertEquals('猫', lua_globals.text4)
        self.assertEquals(42, lua_globals.num2)
