import os

from PyInstaller.utils.hooks.hookutils import collect_data_files


def get_virtual_env_extra_site_files():
    return [
        (
            os.path.join(
                os.path.dirname(__file__),
                '..', 'wpull_env', 'lib',  'python*', '*.txt'
            ),
            './'
        ),
        (
            os.path.join(
                os.path.dirname(__file__),
                '..', 'wpull_env', 'Lib', '*.txt'
            ),
            './'
        )
    ]


datas = collect_data_files('wpull') + get_virtual_env_extra_site_files()
