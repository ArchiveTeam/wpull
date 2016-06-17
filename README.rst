=====
Wpull
=====


Wpull is a Wget-compatible (or remake/clone/replacement/alternative) web
downloader and crawler.

.. image:: https://raw.githubusercontent.com/chfoo/wpull/master/icon/wpull_logo_full.png
   :target: https://github.com/chfoo/wpull
   :alt: A dog pulling a box via a harness.

Notable Features:

* Written in Python: lightweight, modifiable, robust, & scriptable
* Graceful stopping; on-disk database resume
* PhantomJS & youtube-dl integration (experimental)


Install
=======

Wpull uses `Python 3 <http://python.org/download/>`_.

Once Python is installed, download Wpull from PyPI using pip::

    pip3 install wpull

For detailed installation instructions and potential caveats, please see
https://wpull.readthedocs.io/en/master/install.html.


Example Commands
================

To download the About page of Google.com::

    wpull google.com/about

To archive a website::

    wpull billy.blogsite.example \
        --warc-file blogsite-billy \
        --no-check-certificate \
        --no-robots --user-agent "InconspiuousWebBrowser/1.0" \
        --wait 0.5 --random-wait --waitretry 600 \
        --page-requisites --recursive --level inf \
        --span-hosts-allow linked-pages,page-requisites \
        --escaped-fragment --strip-session-id \
        --sitemaps \
        --reject-regex "/login\.php" \
        --tries 3 --retry-connrefused --retry-dns-error \
        --timeout 60 --session-timeout 21600 \
        --delete-after --database blogsite-billy.db \
        --quiet --output-file blogsite-billy.log

To see all options::

    wpull --help


Documentation
=============

Documentation is located at https://wpull.readthedocs.io/. Please have
a look at it before using Wpull's advanced features.


Help
====

Need help? Please see our `Help
<https://wpull.readthedocs.io/en/master/help.html>`_ page which contains
frequently asked questions and support information.

The issue tracker is located at https://github.com/chfoo/wpull/issues.


Dev
===

.. image:: https://travis-ci.org/chfoo/wpull.png
   :target: https://travis-ci.org/chfoo/wpull
   :alt: Travis CI build status

.. image:: https://coveralls.io/repos/chfoo/wpull/badge.png
   :target: https://coveralls.io/r/chfoo/wpull
   :alt: Coveralls report


Contributions and feedback are greatly appreciated. 


Credits
=======

Copyright 2013-2016 by Christopher Foo and others. License GPL v3.

This project contains third-party source code licensed under different terms:

* wpull.backport.logging
* wpull.thirdparty.robotexclusionrulesparser
* wpull.thirdparty.dammit

We would like to acknowledge the authors of GNU Wget as Wpull uses algorithms
from Wget.

