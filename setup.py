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
    'wpull.abstract',
    'wpull.backport',
    'wpull.coprocessor',
    'wpull.database',
    'wpull.document',
    'wpull.document.htmlparse',
    'wpull.driver',
    'wpull.ftp',
    'wpull.ftp.ls',
    'wpull.http',
    'wpull.processor',
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
        'proxy.crt',
        'proxy.key',
    ]},
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
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


if os.environ.get('USE_CX_FREEZE'):
    from cx_Freeze import setup, Executable

    wpull_package_dir = '.'
    wpull_package_src_dir = './wpull/'

    sys.path.insert(0, os.path.dirname(wpull_package_dir))

    extension = '.exe' if platform.system() == 'Windows' else ''

    setup_kwargs['executables'] = [
        Executable(
            os.path.join(wpull_package_src_dir, '__main__.py'),
            targetName='wpull' + extension,
            shortcutName='Wpull ' + version,
        )
    ]
    setup_kwargs['options'] = {
        'build_exe': {
            'includes': [
                'lxml._elementpath',
                'sqlalchemy.dialects.sqlite',
            ],
            'zip_includes': [
                (os.path.join(wpull_package_src_dir, 'cert', 'ca-bundle.pem'),
                 'wpull/cert/ca-bundle.pem'),
            ],
            'include_files': [
                (
                    os.path.join(wpull_package_src_dir, 'driver', 'phantomjs.js'),
                    'phantomjs.js'
                ),
                (
                    os.path.join(wpull_package_src_dir, 'proxy.crt'),
                    'proxy.crt'
                ),
                (
                    os.path.join(wpull_package_src_dir, 'proxy.key'),
                    'proxy.key'
                ),
            ]
        }
    }


if __name__ == '__main__':
    if sys.version_info[0] < 3:
        raise Exception('Sorry, Python 2 is not supported.')

    setup(**setup_kwargs)
