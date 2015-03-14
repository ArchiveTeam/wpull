#!/usr/bin/env python3
import copy
import subprocess
import sys
import distutils.util
import platform
import os.path
import os
import zipfile
import time


def main():
    this_python = sys.executable
    env_dir = os.path.abspath('./wpull_env/')
    is_windows = platform.system() == 'Windows'
    env_bin_dir = 'Scripts' if is_windows else 'bin'
    env_python_exe = 'python.exe' if is_windows else 'python'
    exe_name = 'wpull'
    final_exe_name = 'wpull.exe' if is_windows else 'wpull'

    def run_py(args):
        subprocess.check_call([this_python, '-m'] + list(args))

    def run_env_py(args, get_output=False):
        proc_args = [os.path.join(env_dir, env_bin_dir, env_python_exe), '-m'] + list(args)

        # XXX: On Mac OS X, this variables messes up python and uses the
        # wrong interpreter.
        env = copy.copy(os.environ)
        env.pop('__PYVENV_LAUNCHER__', None)
        env.pop('_', None)

        if get_output:
            return subprocess.check_output(proc_args, env=env)
        else:
            subprocess.check_call(proc_args, env=env)

    print('Initialize virtual env.')
    run_py(['virtualenv', '--always-copy', '--system-site-packages', env_dir])

    print('Check for PyInstaller.')
    try:
        run_env_py(['PyInstaller.main', '--version'])
    except subprocess.CalledProcessError as error:
        print('Returned code', error.returncode)

        print('Install PyInstaller.')
        run_env_py([
            'pip', 'install',
            'git+https://github.com/pyinstaller/pyinstaller@python3#egg=PyInstaller',
        ])

    print('Install packages.')
    run_env_py(['pip', 'install', '-r', '../../requirements.txt'])

    print('Install optional packages.')
    run_env_py(['pip', 'install', 'cchardet'])

    print('Install Wpull.')
    run_env_py(['pip', 'install', '../../'])

    print('Build binary.')
    run_env_py(['PyInstaller.main',
        os.path.join(env_dir, env_bin_dir, 'wpull'),
        '--additional-hooks-dir', 'hooks',
        '--onefile',
        '--name', exe_name,
    ])

    print('Zip.')
    wpull_version = run_env_py(['wpull', '--version'], get_output=True)\
        .decode('ascii').strip()
    platform_string = distutils.util.get_platform()
    python_version = platform.python_version()
    date_string = time.strftime('%Y%m%d%H%M%S', time.gmtime())
    zip_name = 'wpull-{}-{}-{}-{}'.format(
        wpull_version, platform_string, python_version, date_string
    )

    with zipfile.ZipFile(os.path.join('dist', zip_name) + '.zip', 'w',
                         compression=zipfile.ZIP_DEFLATED) as zip_obj:
        zip_obj.write(os.path.join('dist', final_exe_name), final_exe_name)
        zip_obj.write(os.path.join('..', '..', 'README.rst'), 'README.rst')
        zip_obj.write(os.path.join('..', '..', 'LICENSE.txt'), 'LICENSE.txt')

    print('Done.')

if __name__ == '__main__':
    main()
