=====
Wpull
=====


Wpull is a Wget-compatible (or remake/clone/replacement/alternative) web
downloader.

.. image:: https://raw.github.com/chfoo/wpull/master/icon/wpull_logo_full.png
   :target: https://github.com/chfoo/wpull
   :alt: A dog pulling a box via a harness.

Features:

* Written in Python: lightweight & robust
* Familiar Wget options and behavior
* Graceful stopping and resuming
* Python & Lua scripting support
* Modular, extensible, & asynchronous API 

**Currently in beta quality! Some features are not implemented yet and the API
is not considered stable.**


Install
=======

Requires:

* `Python 2.6, 2.7, 3.2, 3.3 (or newer) <http://python.org/download/>`_
* `Tornado <https://pypi.python.org/pypi/tornado>`_
* `Toro <https://pypi.python.org/pypi/toro>`_
* `lxml <https://pypi.python.org/pypi/lxml>`_
* `chardet <https://pypi.python.org/pypi/chardet>`_
* `SQLAlchemy <https://pypi.python.org/pypi/SQLAlchemy>`_
* `Lunatic Python (bastibe version)
  <https://github.com/bastibe/lunatic-python>`_ (optional for Lua support)

Once you install the requirements, install Wpull from PyPI using pip::

    pip3 install wpull

For detailed installation instructions, please see
http://wpull.readthedocs.org/en/master/install.html.


Run
===

To download the About page of Google.com::

    python3 -m wpull google.com/about

To archive a website::

    python3 -m wpull billy.blogsite.example --warc-file blogsite-billy \
    --no-check-certificate \
    --no-robots --user-agent "InconspiuousWebBrowser/1.0" \
    --wait 0.5 --random-wait --waitretry 600 \
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
=============

Documentation is located at http://wpull.readthedocs.org/.


Help
====

Need help? Please see our `Help
<http://wpull.readthedocs.org/en/master/help.html>`_ page which contains 
frequently asked questions and support information.

The issue tracker is located at https://github.com/chfoo/wpull/issues.


Dev
===

.. image:: https://travis-ci.org/chfoo/wpull.png
   :target: https://travis-ci.org/chfoo/wpull
   :alt: Travis CI build status

Contributions and feedback are greatly appreciated. 


Credits
=======

Copyright 2013-2014 by Christopher Foo. License GPL v3.

This project contains third-party source code licensed under different terms:

* backport
* wpull.backport.argparse
* wpull.backport.collections
* wpull.backport.functools
* wpull.backport.tempfile
* wpull.backport.urlparse
* wpull.thirdparty.robotexclusionrulesparser

We would like to acknowledge the authors of GNU Wget as Wpull uses algorithms
from Wget.

