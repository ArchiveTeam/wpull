from PyInstaller.utils.hooks.hookutils import collect_submodules

hiddenimports = collect_submodules('dns')
