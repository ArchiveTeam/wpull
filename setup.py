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


# Get version-appropriate package info via backport.
config = backport.get_config('backport.conf')
if sys.version_info[0] == 3:
    config_section = 'src_package_dir'
else:
    config_section = 'dst_package_dir'
PROJECT_PACKAGES = config.options(config_section)
PROJECT_PACKAGE_DIR = dict(config.items(config_section))


extras = {}
install_requires = [
    'tornado', 'toro', 'lxml', 'chardet',
]

if sys.version_info[0] == 2:
    install_requires.append('futures')
    # Requiring 3to2 doesn't mean it will be installed first
    # Also it might cause confusion by downloading from PyPI which
    # we do not want.
    # install_requires.append('3to2')


if __name__ == '__main__':
    if sys.version_info[0] == 2:
        backport.translate_project('backport.conf')

    setup(name='wpull',
        version=version,
        description='Wget-compatible web downloader.',
        author='Christopher Foo',
        author_email='chris.foo@gmail.com',
        url='https://github.com/chfoo/wpull',
        package_data={'': [
            'cert/ca-bundle.pem',
            'testing/*/*.css',
            'testing/*/*.html',
            'testing/*/*.txt',
        ]},
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
        packages=PROJECT_PACKAGES,
        package_dir=PROJECT_PACKAGE_DIR
)
