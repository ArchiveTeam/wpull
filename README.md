Wpull
=====

**Work in progress!**

Wpull is a Wget-compatible (or remake/clone/replacement/alternative) web downloader.

Features:

* Written in Python
* Modular
* Asynchronous


Install
-------

Requires:

* Python 3.2+
* Tornado, toro, lxml

Dependencies can be installed using pip:

    pip3 install -r requirements.txt


Run
---

To download the homepage of Google.com:

    python3 -m wpull google.com

To see all options:

    python3 -m wpull --help


Todo
----

* lot's of TODO markers in code
* docstrings
* 3to2 support


Credits
-------

Copyright 2013 by Christopher Foo. License GPL v3.

We would like to acknowledge the authors of GNU Wget as Wpull uses algorithms from Wget.

