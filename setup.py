#!/usr/bin/env python

from distutils.core import setup

import os.path
import re
from distutils.version import StrictVersion


def get_version():
    path = os.path.join('wpull', 'version.py')

    with open(path, 'r') as version_file:
        content = version_file.read()
        return re.match(r"__version__ = '(.+)'", content).group(1)


version = get_version()

StrictVersion(version)

setup(name='wpull',
    version=version,
    description='Wget-compatible web downloader.',
    author='Christopher Foo',
    author_email='chris.foo@gmail.com',
    url='',
    packages=['wpull'],
    install_requires=['tornado', 'toro', 'lxml'],
)
