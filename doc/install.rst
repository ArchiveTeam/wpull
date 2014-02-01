============
Installation
============

Requirements
============

Wpull requires the following:

.. ⬇ Please keep this list in sync with the README file. ⬇

* `Python 2.6, 2.7, 3.2, 3.3 (or newer) <http://python.org/download/>`_
* `Tornado <https://pypi.python.org/pypi/tornado>`_
* `Toro <https://pypi.python.org/pypi/toro>`_
* `lxml <https://pypi.python.org/pypi/lxml>`_
* `chardet <https://pypi.python.org/pypi/chardet>`_
* `SQLAlchemy <https://pypi.python.org/pypi/SQLAlchemy>`_
* `Lunatic Python (bastibe version)
  <https://github.com/bastibe/lunatic-python>`_ (optional for Lua support)

For installing Wpull, it is recommended to use `pip installer
<http://www.pip-installer.org/>`_.


Python
++++++

Please obtain the latest Python release from http://python.org/download/
or your package manager. It is recommended to use Python 3.2 or greater.


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

.. Note:: At time of writing, Lunatic Python does not support Python 3.2.

.. Note:: The version of Lunatic Python in the Python Package Index (PyPI)
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


Automatic Install
=================

Once you have installed Python, lxml, and pip, install Wpull with
dependencies automatically from PyPI::

    pip3 install wpull

.. Note:: Python 2 users, please see note in the next subsection.

.. Tip:: Adding the ``--upgrade`` option will upgrade Wpull to the latest
   release. Use ``--no-dependencies`` to only upgrade Wpull.

.. Tip:: Adding the ``--user`` option will install Wpull into your home
   directory.


Python 2.6/2.7
++++++++++++++

Please ensure you have the *latest* lib3to2 from Bitbucket before installing
Wpull::

    pip install hg+https://bitbucket.org/amentajo/lib3to2#egg=3to2

.. Note:: The version in PyPI is out of date.


Manual Install
==============

Install the dependencies::

    pip3 install -r https://raw2.github.com/chfoo/wpull/master/requirements.txt

Install Wpull from GitHub::

    pip3 install git+https://github.com/chfoo/wpull.git#egg=wpull

.. Tip:: Using ``git+https://github.com/chfoo/wpull.git@develop#egg=wpull``
   as the path will install Wpull's develop branch.


Python 2.6/2.7
++++++++++++++

Requires

* `futures <https://pypi.python.org/pypi/futures>`_
* `lib3to2 <https://bitbucket.org/amentajo/lib3to2>`_ (the one on PyPI is
   *very* outdated!)

Install additional dependencies before installing Wpull::

    pip install -r https://raw2.github.com/chfoo/wpull/master/requirements-py2.txt

.. Note:: Invoking ``setup.py`` (with or without commands/options) will
   trigger the 3to2 process automatically. The Python 2 compatible source
   code will be placed in ``py2src_noedit/``. Invoking a Python 2
   interpreter on the original Python 3 source code will result Wpull
   failing to run due to syntax errors.

