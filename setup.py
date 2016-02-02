#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from distutils.version import StrictVersion
import os.path
import re
import os
import sys
import platform


def get_version():
    path = os.path.join('wpull', 'version.py')

    with open(path, 'r') as version_file:
        content = version_file.read()
        return re.search(r"__version__ = u?'(.+)'", content).group(1)


version = get_version()

StrictVersion(version)


PROJECT_PACKAGES = [
    'wpull',
    'wpull.protocol.abstract',
    'wpull.backport',
    'wpull.coprocessor',
    'wpull.database',
    'wpull.document',
    'wpull.document.htmlparse',
    'wpull.driver',
    'wpull.protocol.ftp',
    'wpull.protocol.ftp.ls',
    'wpull.protocol.http',
    'wpull.processor',
    'wpull.proxy',
    'wpull.recorder.',
    'wpull.scraper',
    'wpull.testing',
    'wpull.thirdparty',
]
PROJECT_PACKAGE_DIR = {}


setup_kwargs = dict(
    name='wpull',
    version=version,
    description='Wget-compatible web downloader and crawler.',
    author='Christopher Foo',
    author_email='chris.foo@gmail.com',
    url='https://github.com/chfoo/wpull',
    package_data={'': [
        'cert/ca-bundle.pem',
        'testing/*/*.css',
        'testing/*/*.htm',
        'testing/*/*.html',
        'testing/*/*.txt',
        'testing/*/*.lua',
        'testing/*/*.rst',
        'testing/*/*.js',
        'testing/*/*.png',
        'testing/*/*.xml',
        'testing/*.lua',
        'testing/*.pem',
        'driver/*.js',
        'proxy/proxy.crt',
        'proxy/proxy.key',
    ]},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: File Transfer Protocol (FTP)',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: System :: Archiving',
    ],
    packages=PROJECT_PACKAGES,
    package_dir=PROJECT_PACKAGE_DIR,
)

setup_kwargs['install_requires'] = [
    'tornado', 'trollius', 'chardet', 'sqlalchemy',
    'namedlist', 'html5lib', 'dnspython3',
]

setup_kwargs['scripts'] = ['scripts/wpull', 'scripts/wpull3']


if __name__ == '__main__':
    if sys.version_info[0] < 3:
        raise Exception('Sorry, Python 2 is not supported.')

    setup(**setup_kwargs)
