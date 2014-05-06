#!/usr/bin/env python3
import os.path


MODULES = [
    'actor',
    'app',
    'async',
    'cache',
    'cookie',
    'collections',
    'conversation',
    'converter',
    'database',
    'debug',
    'decompression',
    'document',
    'engine',
    'errors',
    'factory',
    'hook',
    'http',
    'http.client',
    'http.connection',
    'http.request',
    'http.util',
    'http.web',
    'iostream',
    'item',
    'namevalue',
    'network',
    'options',
    'phantomjs',
    'processor',
    'proxy',
    'recorder',
    'robotstxt',
    'scraper',
    'stats',
    'string',
    'url',
    'urlfilter',
    'util',
    'version',
    'waiter',
    'warc',
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
