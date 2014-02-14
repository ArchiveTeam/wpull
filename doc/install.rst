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
* `cssutils <https://pypi.python.org/pypi/cssutils>`_ (optional for web browser engine)
* `pyv8 <https://code.google.com/p/pyv8/>`_ (optional for web browser engine)

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


Lua Scripting (Optional)
++++++++++++++++++++++++

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


PyV8 (Optional)
+++++++++++++++

To enable web browser engine support, V8 and Py8 must be installed. V8 is a JavaScript engine. At time of writing, no recent pre-built binaries are available.

Prerequisites:

* SCons
* Boost

On Debian/Ubuntu systems, you can install these with::

    apt-get install scons libboost-python-dev libboost-system-dev libboost-thread-dev

Download the source code with SVN::

    svn checkout http://v8.googlecode.com/svn/trunk/ v8-read-only
    svn checkout http://pyv8.googlecode.com/svn/trunk/ pyv8-read-only

If Python 3, seek to the line with ``boost_libs``. Modify ``boost_python`` to match the appropriate Python version. For example, ``boost_python-py32`` or ``boost_python-py33``. 

If Python 3, patch setup.py::

    2to3 pyv8-read-only/setup.py -w

Specify the location of V8 source code in the environment variable ``V8_HOME``. Then install PyV8. On Linux, use::

    V8_HOME=`pwd`/v8-read-only pip3 install ./pyv8-read-only

It will take a moment to install.

These instructions were based on http://blog.dinotools.de/2013/02/27/python-build-pyv8-for-python3-on-ubuntu/.

Other Optional
++++++++++++++

Other optional libraries can be installed using (where NAME is the name of the Python library)::

    pip3 install NAME


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
* `lib3to2 <https://bitbucket.org/amentajo/lib3to2>`_
   (the one on PyPI is *very* outdated!)

Install additional dependencies before installing Wpull::

    pip install -r https://raw2.github.com/chfoo/wpull/master/requirements-py2.txt

.. Note:: Invoking ``setup.py`` (with or without commands/options) will
   trigger the 3to2 process automatically. The Python 2 compatible source
   code will be placed in ``py2src_noedit/``. Invoking a Python 2
   interpreter on the original Python 3 source code will result Wpull
   failing to run due to syntax errors.

