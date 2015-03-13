pyinstaller
===========

The `runner.py` script is designed to install dependencies into a virtualenv.

It currently works in Debian/Ubuntu, Windows 7, and Mac OS 10.10.


Quick Start
===========

1. Install virtualenv if not already installed. For example, `pip3 install virtualenv --user`.
2. Run the script. Use something like `python3 runner.py`. It will download pyinstaller and all of Wpull's dependencies.


Linux
-----

If libpython is not found, you may need to copy it manually. For example, copy from `/usr/local/lib/libpython3.4m.so.1.0` to the same directory as `runner.py`. If you don't have a `.so` file but only a `.a` file, you need to build Python with passing `--enabled-shared` to `./configure`.


Windows
-------

You will need to install PyWin32 that matches the same Python build (same version and 32/64-bit). Also install lxml and SQLAlchemy using the Windows or Wheel (`.whl`) installers if you do not a have a C extension build environment. You may comment out the optional cchardet in the script if you cannot find a installer for it.


Mac OS X
--------

Nothing in particular of note.

