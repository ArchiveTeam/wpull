import os
import platform

from PyInstaller.utils.hooks import collect_data_files


def get_virtual_env_extra_site_files():
    if platform.system() == 'Windows':
        return [
            (
                os.path.join(
                    os.path.dirname(__file__),
                    '..', 'wpull_env', 'Lib', '*.txt'
                ),
                './'
            )
        ]
    else:
        return [
            (
                os.path.join(
                    os.path.dirname(__file__),
                    '..', 'wpull_env', 'lib',  'python*', '*.txt'
                ),
                './'
            ),
        ]


datas = collect_data_files('wpull') + get_virtual_env_extra_site_files()
