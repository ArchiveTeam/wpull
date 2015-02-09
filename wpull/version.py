# encoding=utf-8
'''Version information.

.. data:: __version__

   A string conforming to `Semantic Versioning
   Guidelines <http://semver.org/>`_

.. data:: version_info

    A tuple in the same format of :data:`sys.version_info`
'''
import re


RELEASE_LEVEL_MAP = {
    'a': 'alpha',
    'b': 'beta',
    'c': 'candidate'
}


def get_version_tuple(string):
    '''Return a version tuple from a string.'''
    match = re.match(r'(\d+)\.(\d+)\.?(\d*)([abc]?)(\d*)', string)
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    level = RELEASE_LEVEL_MAP.get(match.group(4), 'final')
    serial = int(match.group(5) or 0)

    return major, minor, patch, level, serial


__version__ = '0.1006.1'
version_info = get_version_tuple(__version__)
