#!/usr/bin/env python3
import os.path


MODULES = [
    'actor',
    'app',
    'cache',
    'conversation',
    'converter',
    'database',
    'document',
    'engine',
    'errors',
    'extended',
    'factory',
    'hook',
    'http',
    'namevalue',
    'network',
    'options',
    'processor',
    'recorder',
    'robotstxt',
    'scraper',
    'stats',
    'url',
    'util',
    'version',
    'waiter',
    'warc',
    'web',
    'wrapper',
    'writer',
]


def main():
    for name in MODULES:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '{0}.rst'.format(name)
        )
        with open(path, 'w') as out_file:
            out_file.write('.. This document was automatically generated.\n')
            out_file.write('   DO NOT EDIT!\n\n')

            title = ':mod:`{0}` Module'.format(name)
            out_file.write(title + '\n')
            out_file.write('=' * len(title) + '\n\n')
            out_file.write('.. automodule:: wpull.{0}\n'.format(name))
            out_file.write('    :members:\n')
            out_file.write('    :show-inheritance:\n')
            out_file.write('    :private-members:\n')
            out_file.write('    :special-members:\n')
            out_file.write('    :exclude-members: __dict__,__weakref__\n')


if __name__ == '__main__':
    main()
