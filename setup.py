#!/usr/bin/env python

from distutils.core import setup
from distutils.version import StrictVersion
import os.path
import re
import os
import sys


def get_version():
    path = os.path.join('wpull', 'version.py')

    with open(path, 'r') as version_file:
        content = version_file.read()
        return re.search(r"__version__ = u?'(.+)'", content).group(1)


version = get_version()

StrictVersion(version)


PROJECT_PACKAGES = [
    'wpull',
    'wpull.backport',
    'wpull.http',
    'wpull.processor',
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
        'testing/*/*.html',
        'testing/*/*.txt',
        'testing/*/*.lua',
        'testing/*/*.rst',
        'testing/*/*.js',
        'testing/*/*.png',
        'testing/*/*.xml',
        'testing/*.lua',
        '*.js',
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
    'tornado', 'trollius', 'lxml', 'chardet', 'sqlalchemy',
    'namedlist',
]

setup_kwargs['scripts'] = ['scripts/wpull', 'scripts/wpull3']


if os.environ.get('USE_CX_FREEZE'):
    from cx_Freeze import setup, Executable

    wpull_package_dir = PROJECT_PACKAGE_DIR['wpull']

    sys.path.insert(0, os.path.dirname(wpull_package_dir))

    setup_kwargs['executables'] = [
        Executable(
            os.path.join(wpull_package_dir, '__main__.py'),
            targetName='wpull-' + version,
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
                os.path.join(wpull_package_dir, 'cert', 'ca-bundle.pem'),
            ],
            'include_files': [
                (
                    os.path.join(wpull_package_dir, 'phantomjs.js'),
                    'phantomjs.js'
                ),
            ]
        }
    }


if __name__ == '__main__':
    if sys.version_info[0] < 3:
        raise Exception('Sorry, Python 2 is not supported.')

    setup(**setup_kwargs)
