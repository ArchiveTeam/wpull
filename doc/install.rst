============
Installation
============

Requirements
============

Wpull requires the following:

* `Python 3.2 or greater <http://python.org/download/>`_
* `Tornado <https://pypi.python.org/pypi/tornado>`_
* `Trollius <https://pypi.python.org/pypi/trollius>`_
* `html5lib <https://pypi.python.org/pypi/html5lib>`_

  * Or `lxml <https://pypi.python.org/pypi/lxml>`_ for faster
    but much worse HTML parsing

* `chardet <https://pypi.python.org/pypi/chardet>`_

  * Or `cchardet <https://pypi.python.org/pypi/cchardet>`_ for faster
    version of chardet

* `SQLAlchemy <https://pypi.python.org/pypi/SQLAlchemy>`_

The following are optional:

* `Lunatic Python (bastibe version)
  <https://github.com/bastibe/lunatic-python>`_ for Lua support
* `Manhole <https://pypi.python.org/pypi/manhole>`_ for a REPL debugging socket
* `PhantomJS <http://phantomjs.org/>`_ for capturing interactive
  JavaScript pages
* `youtube-dl <https://rg3.github.io/youtube-dl/>`_ for downloading complex
  video streaming sites

For installing Wpull, it is recommended to use `pip installer
<http://www.pip-installer.org/>`_.

Wpull is officially supported in a Unix-like environment.


Automatic Install
=================

Once you have installed Python, lxml, and pip, install Wpull with
dependencies automatically from PyPI::

    pip3 install wpull

.. Tip:: Adding the ``--upgrade`` option will upgrade Wpull to the latest
   release. Use ``--no-dependencies`` to only upgrade Wpull.
   
   Adding the ``--user`` option will install Wpull into your home
   directory.

Automatic install is usually the best option. However, there may be
outstanding fixes to bugs that are not yet released to PyPI. In this
case, use the manual install.


Manual Install
==============

Install the dependencies known to work with Wpull::

    pip3 install -r https://raw2.github.com/chfoo/wpull/master/requirements.txt

Install Wpull from GitHub::

    pip3 install git+https://github.com/chfoo/wpull.git#egg=wpull

.. Tip:: Using ``git+https://github.com/chfoo/wpull.git@develop#egg=wpull``
   as the path will install Wpull's develop branch.


Pre-built Binaries
==================

Wpull has pre-built binaries located at https://launchpad.net/wpull/+download. These are unsupported and may not be up to date.


Caveats
=======

Python
++++++

Please obtain the latest Python release from http://python.org/download/
or your package manager. It is recommended to use Python 3.3 or greater.
Versions 3.2, 3.3, 3.4 are officially supported.

PyPy 2.3.1 (Python 3.2 implementation) is supported.

Python 2 is not supported.


lxml
++++

It is recommended that lxml is obtained through an installer
or pre-built package. Windows packages are provided on
https://pypi.python.org/pypi/lxml. Debian/Ubuntu users
should install ``python3-lxml``. For more information, see
http://lxml.de/installation.html.


pip
+++

If pip is not installed on your system yet, please follow the instructions
at http://www.pip-installer.org/en/latest/installing.html to install
pip. Note for Linux users, ensure you are executing the appropriate
Python version when installing pip.


Lua Scripting
+++++++++++++

To enable optional Lua scripting support, Lunatic Python (bastibe version)
can be installed using pip::

    pip3 install git+https://github.com/bastibe/lunatic-python.git#egg=lunatic-python

.. Note:: At time of writing, Lunatic Python uses Lua 5.2. If you desire a
   different version of Lua, please see below.

   At time of writing, Lunatic Python does not support Python 3.2.

   The version of Lunatic Python in the Python Package Index (PyPI)
   is out of date.


Specify Lua version
-------------------

Download lunatic-python from https://github.com/bastibe/lunatic-python using
the "Download ZIP" link or ``git clone``.

Inside ``setup.py``, edit ``LUAVERSION`` to reflect the current Lua library
installed. On Debian/Ubuntu it is known by ``libluaX.Y-dev``.

Run pip to install Lunatic Python with ``LOCATION`` replaced with the
location of the Lunatic Python source code.::

    pip install LOCATION


PhantomJS (Optional)
++++++++++++++++++++

It is recommended to download a prebuilt binary build from
http://phantomjs.org/download.html.

