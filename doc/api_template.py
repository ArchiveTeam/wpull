#!/usr/bin/env python3
import os.path


def find_modules():
    package_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'wpull'
    )
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = sorted(dirs)
        for filename in sorted(files):
            if os.path.splitext(filename)[1] != '.py':
                continue

            module_path = os.path.relpath(
                os.path.join(root, filename), package_dir)

            parts = module_path.split('/')
            parts[-1] = parts[-1].replace('.py', '')
            if parts[0] in ('thirdparty', 'backport', 'testing'):
                continue
            if parts[-1] == '__main__' or parts[-1].endswith('_test'):
                continue
            if parts[-1] == '__init__':
                module_name = '.'.join(parts[:-1])
            else:
                module_name = '.'.join(parts)
            if module_name:
                yield module_name


def main():
    modules = tuple(sorted(find_modules()))

    for name in modules:
        print(name)
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'api',
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
            out_file.write('    :undoc-members:\n')
            # out_file.write('    :private-members:\n')
            # out_file.write('    :special-members:\n')
            # out_file.write('    :exclude-members: __dict__,__weakref__\n')


if __name__ == '__main__':
    main()
