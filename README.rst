Wpull
=====

Wpull is a Wget-compatible (or remake/clone/replacement/alternative) web downloader.

Features:

* Written in Python
* Modular
* Asynchronous

.. image:: https://travis-ci.org/chfoo/wpull.png
   :target: https://travis-ci.org/chfoo/wpull
   :alt: Travis CI build status

**Currently in beta quality! Some features are not implemented yet and the API is not considered stable.**

Install
+++++++

Requires:

* `Python 2.6, 2.7, or 3.2+ <http://python.org/download/>`_
* `Tornado <https://pypi.python.org/pypi/tornado>`_
* `Toro <https://pypi.python.org/pypi/toro>`_
* `lxml <https://pypi.python.org/pypi/lxml>`_

Install Wpull from GitHub::

    pip3 install git+https://github.com/chfoo/wpull.git#egg=wpull

Dependencies can be installed using pip as well::

    pip3 install -r requirements.txt

Tip: Adding the ``--user`` option will install into your home directory.

Python 2.6/2.7
--------------

Install lib3to2 and additional requirements before installing Wpull::

    pip install hg+https://bitbucket.org/amentajo/lib3to2#egg=3to2
    pip install -r requirements-2py.txt

Invoking ``setup.py`` will trigger the 3to2 process. The Python 2 compatible source code will be placed in ``py2src_noedit/``.

Run
+++

To download the About page of Google.com::

    python3 -m wpull google.com/about

To archive a website::

    python3 -m wpull billy.blogsite.example --warc-file blogsite-billy \
    --no-robots --user-agent "InconspiuousWebBrowser/1.0" \
    --wait 0.5 --random-wait --wait-retry 600 \
    --page-requisites --recursive --level inf \
    --span-hosts --domains blogsitecdn.example,cloudspeeder.example \
    --hostnames billy.blogsite.example \
    --reject-regex "/login\.php"  \
    --tries inf --retry-connrefused --retry-dns-error \
    --delete-after --database blogsite-billy.db \
    --quiet --output-file blogsite-billy.log

To see all options::

    python3 -m wpull --help


Documentation
+++++++++++++

Documentation is not yet written.

API Note: This library is not thread safe.


Help
++++

Issues can be reported to the issue tracker: https://github.com/chfoo/wpull/issues.


Todo
++++

* lot's of TODO markers in code
* docstrings
* sphinx doc config


Credits
+++++++

Copyright 2013-2014 by Christopher Foo. License GPL v3.

This project contains third-party source code licensed under different terms:

* backport
* wpull.backport.argparse
* wpull.backport.collections
* wpull.backport.functools
* wpull.backport.tempfile
* wpull.thirdparty.robotexclusionrulesparser

We would like to acknowledge the authors of GNU Wget as Wpull uses algorithms from Wget.

