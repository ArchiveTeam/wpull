#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2011-2014 Shawn Brown. License BSD 3-Clause ("BSD New").
# Version 727027eadace
assert ''.__class__.__name__ == 'str', 'Must not translate with 3to2.'

import itertools
import re
import shutil
import sys
import os

try:
    from io import StringIO
    if sys.version_info[:2] == (2, 7):  # For version 2.7 only.
        _StringIO = StringIO
        class StringIO(_StringIO):
            def __init__(self, initial_value='', newline=None):
                initial_value = unicode(initial_value)
                return _StringIO.__init__(self, initial_value, newline)
except ImportError:
    from StringIO import StringIO

try:
    import configparser  # Renamed in version 3.0.
except ImportError:
    import ConfigParser as configparser

try:
    configparser.ConfigParser.read_string  # New in version 3.2.
except AttributeError:
    def _read_string(self, string, source='<string>'):
        return self.readfp(StringIO(string), source)
    configparser.ConfigParser.read_string = _read_string

try:
    os.path.relpath
except AttributeError:
    def _relpath(path, start=os.path.curdir):
        """Taken from Python 2.7 Standard Libary (posixpath.py)."""
        if not path:
            raise ValueError("no path specified")

        start_list = [x for x in os.path.abspath(start).split(os.path.sep) if x]
        path_list = [x for x in os.path.abspath(path).split(os.path.sep) if x]

        i = len(os.path.commonprefix([start_list, path_list]))

        rel_list = [os.path.pardir] * (len(start_list) - i) + path_list[i:]
        if not rel_list:
            return curdir
        return os.path.join(*rel_list)
    os.path.relpath = _relpath

try:
    from subprocess import CalledProcessError  # New in version 2.5.
except ImportError:
    class CalledProcessError(OSError):
        def __init__(self, returncode, cmd, output=None):
            message = "Command '%s' returned non-zero exit status %s" \
                % (cmd.__repr__(), returncode)
            OSError.__init__(self, message)

try:
    from subprocess import check_call  # New in version 2.5.
except ImportError:
    from subprocess import call as _call
    def check_call(popenargs, *args, **kwargs):
        retcode = _call(popenargs, *args, **kwargs)
        if retcode != 0:
            raise CalledProcessError(retcode, popenargs)
        return retcode


_token_file = '.translated_code'
_config_file = 'backport.ini'

__version__ = '0.2.0'
__url__ = 'http://code.google.com/p/backport/'
__all__ = ['get_config',
           'translate_project',
           'discover_tests',
           'run_tests',
           'redirect_import']


def get_config(config_fname=None):
    global _config_file
    if not config_fname:
        config_fname = _config_file

    if not os.path.exists(config_fname):
        msg = ('Backport config file - %s - is missing.' % config_fname)
        raise Exception(msg)

    # Open file using version 2.4 compatible syntax.
    fp = None
    try:
        fp = open(config_fname)
        config_string = fp.read()
    finally:
        if fp:
            fp.close()

    return _get_config(config_string, config_fname)


def _get_config(config_string, config_fname='<string>'):
    """ """
    config = configparser.ConfigParser()
    config.read_string(config_string, config_fname)

    # Test for required sections.
    for section in ['src_package_dir', 'dst_package_dir', 'command']:
        if not config.has_section(section):
            msg = '[%s] section is missing from config file.' % section
            raise configparser.NoSectionError(msg)

    # Get paths.
    def getopt(x):
        options = config.options(x)
        if len(options) == 0:
            raise Exception('Section %s contains no options.' % x)
        return [(x, option) for option in options]
    package_options = getopt('src_package_dir') + getopt('dst_package_dir')

    # Normalize package options (names) and values (paths).
    for section, option in package_options:
        value = config.get(section, option)
        value = os.path.normpath(value)
        config.remove_option(section, option)
        config.set(section, str(option), value)

    # Assert that src and dst package names match.
    src_keys = set(config.options('src_package_dir'))
    dst_keys = set(config.options('dst_package_dir'))
    assert src_keys == dst_keys, ('Mismatched package names.  The packages '
                                  'in src_package_dir and dst_package_dir '
                                  'must match.')

    # Assert that src_package_dir and dst_package_dir use same relative
    # directroy structure.
    def noprefix(package_dir):
        option, value = zip(*config.items(package_dir))  # <- nonlocal config
        length = len(os.path.commonprefix(value))
        value = [x[length:] for x in value]  # Slice common prefix.
        return dict(zip(option, value))
    if noprefix('src_package_dir') != noprefix('dst_package_dir'):
        raise Exception('src and dst directory paths do not have same internal structure')

    return config


def _get_filenames(top):
    """ """
    # Get directory (d) and list of file names (f).
    all_filenames = [(d, f) for d, _, f in os.walk(top)]
    all_filenames = [x for x in all_filenames if _isprojectdir(x[0])]

    # Make dir path relative to `top`.
    toplen = len(top)
    all_filenames = [(d[toplen:], f) for d, f in all_filenames]
    all_filenames = [(d.lstrip(os.sep), f) for d, f in all_filenames]

    # Make file paths.
    all_filenames = [_mkfilepath(d, f) for d, f in all_filenames]
    all_filenames = itertools.chain(*all_filenames)

    return all_filenames


def _isprojectfile(x):
    return not x.endswith('.pyc')
    # TODO!!!: and not current file


def _isprojectdir(x):
    global _token_file
    return not x.endswith('__pycache__') and not x.endswith(_token_file)


def _mkfilepath(dirpath, filenames):
    filenames = [name for name in filenames if _isprojectfile(name)]
    return [os.path.join(dirpath, name) for name in filenames]


def _pathdict_from_fnames(source, destination, fnames):
    def mktup(src, dst, name):
        key = os.path.join(src, name)
        val = os.path.join(dst, name)
        return (key, val)

    return dict(mktup(source, destination, x) for x in fnames)


def _pathdict_from_dicts(pathdicts):
    pathdict = dict()
    for x in pathdicts:
        pathdict.update(x)
    return pathdict


def _mk_dstdir(dirname):
    global _token_file
    dirname = os.path.normpath(dirname)
    parts = dirname.split(os.sep)

    path = ''
    for part in parts:
        path = os.path.join(path, part)

        tokenpath = os.path.join(path, _token_file)
        if os.path.exists(path):
            message = ("The path '%s' exists but token file '%s' is "
                       "missing.  This directory appears to be used "
                       "for another purpose!" % (path, _token_file))
            assert os.path.exists(tokenpath), message
        else:
            os.makedirs(path)
            open(tokenpath, 'wb').close()


def _filter_paths(pathdicts, config_mtime=0):
    def fn(item, config_mtime):
        src, dst = item
        src_mtime = max(os.path.getmtime(src), config_mtime)
        return not os.path.exists(dst) or src_mtime > os.path.getmtime(dst)

    filtered = [x for x in pathdicts.items() if fn(x, config_mtime)]
    return dict(filtered)


def _build_command(command_items, fname):
    command_lst = []
    for pat, cmd in command_items:
        try:
            if re.search(pat, fname) is not None:
                return list(re.split('\s+', cmd)) + [fname]  # <- EXIT!
        except re.error:
            raise Exception('Command pattern - %s - is not a valid regular expression.' % pat)

    return None


def _get_all_pathdicts(src_items, dst_items):
    # Item keys are expected to match each other.
    dst_dict = dict(dst_items)
    pathdicts = []
    for package, source in src_items:
        assert os.path.exists(source), 'Source package directory - %s - not found.' % source
        destination = dst_dict[package]
        if os.path.isdir(source):
            fnames = _get_filenames(source)
            single_pathdict = _pathdict_from_fnames(source, destination, fnames)
        else:
            source = os.path.normpath(source)
            destination = os.path.normpath(destination)
            single_pathdict = {source: destination}
        pathdicts.append(single_pathdict)

    return _pathdict_from_dicts(pathdicts)


def translate_project(config_file=_config_file, stdout=None, stderr=None):
    global _token_file

    if not os.path.exists(config_file):
        msg = ('Backport config file - %s - is missing.' % config_file)
        raise Exception(msg)

    config = get_config(config_file)

    # Options in src_package_dir and dst_package_dir are guaranteed
    # to be the same via `get_config()`.
    src_items = config.items('src_package_dir')
    dst_items = config.items('dst_package_dir')
    all_paths = _get_all_pathdicts(src_items, dst_items)
    assert len(all_paths) > 0, 'Source packages contain no files.'

    # Get new or modified file paths.
    config_mtime = max(os.path.getmtime(os.path.abspath(__file__)),
                       os.path.getmtime(config_file))
    paths_to_update = _filter_paths(all_paths, config_mtime)

    # Make destination directories.
    dstdirs = set(os.path.dirname(x) for x in paths_to_update.values())
    for dirname in dstdirs:
        _mk_dstdir(dirname)

    # Find unused files.
    paths_to_remove = []
    for package in config.options('dst_package_dir'):
        destination = config.get('dst_package_dir', package)
        fnames = _get_filenames(destination)
        fnames = [os.path.join(destination, x) for x in fnames]
        paths_to_remove.append(list(fnames))
    paths_to_remove = set(itertools.chain(*paths_to_remove))
    paths_to_remove = set([x for x in paths_to_remove if not x.endswith(os.sep + _token_file)])
    paths_to_remove = paths_to_remove - set(all_paths.values())

    # Delete out-of-date or unused files.
    for path in paths_to_remove:
        os.remove(path)

    # Copy files.
    for srcpath, dstpath in paths_to_update.items():
        shutil.copy2(srcpath, dstpath)
        os.utime(dstpath, None)  # Update last-modified time.

    # Build commands.
    all_commands = []
    command_items = config.items('command')
    for x in paths_to_update.values():
        foo = _build_command(command_items, x)
        all_commands.append(foo)
    all_commands = [x for x in all_commands if x]

    # Run commands.
    try:
        for cmd in all_commands:
            check_call(cmd, stdout=stdout, stderr=stderr)
    except OSError:
        raise OSError('Bad command: ' + ' '.join(cmd))


#################################
# TEST RUNNER SUPPORT
#################################
import unittest
import traceback
import imp
from fnmatch import fnmatch

_VALID_MODULE_NAME = re.compile(r'[_a-z]\w*\.py$', re.IGNORECASE)

class _TestDiscoverer(object):
    """Wraps unittest.TestLoader instance and includes test discovery tools
    for use across target versions of Python (including 2.4).  The methods
    in this class were adapted from the Python Standard Library."""

    def __init__(self):
        self._loader = unittest.TestLoader()
        self._top_level_dir = None

    def discover(self, start_dir, pattern='test*.py', top_level_dir=None):
        set_implicit_top = False
        if top_level_dir is None and self._top_level_dir is not None:
            # make top_level_dir optional if called from load_tests in a package
            top_level_dir = self._top_level_dir
        elif top_level_dir is None:
            set_implicit_top = True
            top_level_dir = start_dir

        top_level_dir = os.path.abspath(top_level_dir)

        if not top_level_dir in sys.path:
            sys.path.insert(0, top_level_dir)
        self._top_level_dir = top_level_dir

        is_not_importable = False
        if os.path.isdir(os.path.abspath(start_dir)):
            start_dir = os.path.abspath(start_dir)
            if start_dir != top_level_dir:
                is_not_importable = not os.path.isfile(os.path.join(start_dir, '__init__.py'))
        else:  # support discovery from dotted module names
            try:
                __import__(start_dir)
            except ImportError:
                is_not_importable = True
            else:
                the_module = sys.modules[start_dir]
                top_part = start_dir.split('.')[0]
                start_dir = os.path.abspath(os.path.dirname((the_module.__file__)))
                if set_implicit_top:
                    self._top_level_dir = self._get_directory_containing_module(top_part)
                    sys.path.remove(top_level_dir)

        if is_not_importable:
            raise ImportError('Start directory is not importable: %r' % start_dir)

        tests = list(self._find_tests(start_dir, pattern))
        return self._loader.suiteClass(tests)

    def _get_directory_containing_module(self, module_name):
        module = sys.modules[module_name]
        full_path = os.path.abspath(module.__file__)

        if os.path.basename(full_path).lower().startswith('__init__.py'):
            return os.path.dirname(os.path.dirname(full_path))
        else:
            return os.path.dirname(full_path)

    def _get_name_from_path(self, path):
        path = os.path.splitext(os.path.normpath(path))[0]
        _relpath = os.path.relpath(path, self._top_level_dir)
        assert not os.path.isabs(_relpath), 'Path must be within the project'
        assert not _relpath.startswith('..'), 'Path must be within the project'

        name = _relpath.replace(os.path.sep, '.')
        return name

    def _make_failed_import_test(self, name, suiteClass):
        message = 'Failed to import test module: %s\n%s' % (name, traceback.format_exc())
        return self._make_failed_test('ModuleImportFailure', name, ImportError(message),
                                      suiteClass)

    def _make_failed_test(self, classname, methodname, exception, suiteClass):
        def testFailure(self):
            raise exception
        attrs = {methodname: testFailure}
        TestClass = type(classname, (unittest.TestCase,), attrs)
        return suiteClass((TestClass(methodname),))

    def _get_module_from_name(self, name):
        __import__(name)
        return sys.modules[name]

    def _find_tests(self, start_dir, pattern):
        global _VALID_MODULE_NAME
        paths = os.listdir(start_dir)

        for path in paths:
            full_path = os.path.join(start_dir, path)
            if os.path.isfile(full_path):
                if not _VALID_MODULE_NAME.match(path):
                    continue  # valid Python identifiers only
                if not fnmatch(path, pattern):
                    continue
                name = self._get_name_from_path(full_path)
                try:
                    module = self._get_module_from_name(name)
                except:
                    yield self._make_failed_import_test(name, self._loader.suiteClass)
                else:
                    mod_file = os.path.abspath(getattr(module, '__file__', full_path))
                    realpath = os.path.splitext(mod_file)[0]
                    fullpath_noext = os.path.splitext(full_path)[0]
                    if realpath.lower() != fullpath_noext.lower():
                        module_dir = os.path.dirname(realpath)
                        mod_name = os.path.splitext(os.path.basename(full_path))[0]
                        expected_dir = os.path.dirname(full_path)
                        msg = ('%r module incorrectly imported from %r. Expected %r. '
                               'Is this module globally installed?')
                        raise ImportError(msg % (mod_name, module_dir, expected_dir))
                    yield self._loader.loadTestsFromModule(module)

            elif os.path.isdir(full_path):
                if not os.path.isfile(os.path.join(full_path, '__init__.py')):
                    continue

                load_tests = None
                tests = None
                if fnmatch(path, pattern):
                    name = self._get_name_from_path(full_path)
                    package = self._get_module_from_name(name)
                    load_tests = getattr(package, 'load_tests', None)
                    tests = self._loader.loadTestsFromModule(package, use_load_tests=False)

                if load_tests is None:
                    if tests is not None:
                        yield tests  # tests loaded from package file
                    for test in self._find_tests(full_path, pattern):
                        yield test  # recursing into the package
                else:
                    try:
                        yield load_tests(self._loader, tests, pattern)
                    except Exception:
                        yield _make_failed_load_tests(package.__name__, 'error loading tests',
                                                      self._loader.suiteClass)


class _AlternateFinder(object):
    """Finder/loader to redirect import requests for one module to an
    alternate module."""
    def __init__(self, orig_name, alt_name=None, alt_path=None):
        self.original = orig_name
        if alt_name:
            self.alternate = alt_name
        else:
            assert alt_path, 'Must specify alt_name or alt_path.'
            self.alternate = orig_name
        self.path = alt_path

        if orig_name in sys.modules:
            raise Exception('Cannot redirect - already imported.')

    def find_module(self, fullname, path=None):
        fullname = fullname.split('.')
        if self.original != fullname[0]:
            return None  # <- EXIT!

        # Replace original parent with alternate.
        fullname = [self.alternate] + fullname[1:]

        fh = None
        path = self.path
        for name in fullname:
            if fh:
                fh.close()

            if not path:
                fh, path, desc = imp.find_module(name, None)
            else:
                fh, path, desc = imp.find_module(name, [path])

        return _AlternateLoader(fh, path, desc)


class _AlternateLoader(object):
    def __init__(self, fh, path, desc):
        self.fh = fh
        self.path = path
        self.desc = desc

    def load_module(self, fullname):
        mod = imp.load_module(fullname, self.fh, self.path, self.desc)
        if not hasattr(mod, '__loader__'):
            mod.__loader__ = self
        if self.fh:
            self.fh.close()
        return mod


def discover_tests(start_dir, pattern='test*.py', top_level_dir=None):
    return _TestDiscoverer().discover(start_dir, pattern, top_level_dir)


def run_tests(test_suite):
    return unittest.TextTestRunner().run(test_suite)


def redirect_import(orig_name, alt_name=None, alt_path=None):
    redirect = _AlternateFinder(orig_name, alt_name, alt_path)
    sys.meta_path.insert(0, redirect)  # Register import hook.


if __name__ == '__main__':
    translate_project()
