#!/usr/bin/env python

from distutils.core import setup
from distutils.version import StrictVersion
import os.path
import re
import sys

import backport


def get_version():
    path = os.path.join('wpull', 'version.py')

    with open(path, 'r') as version_file:
        content = version_file.read()
        return re.search(r"__version__ = '(.+)'", content).group(1)


version = get_version()

StrictVersion(version)

SOURCE_PACKAGE = 'wpull'
TRANSLATED_PACKAGE = 'py2src_noedit/wpull/'


if sys.version_info[0] == 2:
    PACKAGE = TRANSLATED_PACKAGE
else:
    PACKAGE = SOURCE_PACKAGE


extras = {}
install_requires = [
    'tornado', 'toro', 'lxml',
]

if sys.version_info[0] == 2:
    extras['package_dir'] = {SOURCE_PACKAGE: TRANSLATED_PACKAGE}
    install_requires.append('futures')


if __name__ == '__main__':
    if sys.version_info[0] == 2:
        backport.translate_project('backport.conf')
        backport.redirect_import(SOURCE_PACKAGE, TRANSLATED_PACKAGE)

    setup(name='wpull',
        version=version,
        description='Wget-compatible web downloader.',
        author='Christopher Foo',
        author_email='chris.foo@gmail.com',
        url='https://github.com/chfoo/wpull',
        packages=[
            'wpull',
            'wpull.backport',
            'wpull.testing',
            'wpull.thirdparty',
        ],
        package_data={'': ['testing/*/*.html', 'testing/*/*.css']},
        install_requires=install_requires,
        classifiers=[
            'Development Status :: 4 - Beta',
            'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
            'Programming Language :: Python :: 2.6',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3.2',
            'Programming Language :: Python :: 3.3',
            'Topic :: Internet :: WWW/HTTP',
            'Topic :: System :: Archiving',
        ],
        **extras
)
