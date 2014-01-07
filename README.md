Wpull
=====

Wpull is a Wget-compatible (or remake/clone/replacement/alternative) web downloader.

Features:

* Written in Python
* Modular
* Asynchronous

[![Build Status](https://travis-ci.org/chfoo/wpull.png)](https://travis-ci.org/chfoo/wpull)

**Currently in beta quality! Some features are not implemented yet and the API is not considered stable.**

Install
-------

Requires:

* Python 2.6, 2.7, or 3.2+
* Tornado
* toro
* lxml
* robotexclusionrulesparser

Install from GitHub:

    pip3 install git+https://github.com/chfoo/wpull.git#egg=wpull

Dependencies can be installed using pip as well:

    pip3 install -r requirements.txt

Tip: Adding the `--user` option will install into your home directory.

### Python 2.6/2.7

Install lib3to2 before installing Wpull:

    pip install hg+https://bitbucket.org/amentajo/lib3to2#egg=3to2

Run
---

To download the About page of Google.com:

    python3 -m wpull google.com/about

To archive a website:

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

To see all options:

    python3 -m wpull --help


Todo
----

* lot's of TODO markers in code
* docstrings


Credits
-------

Copyright 2013-2014 by Christopher Foo. License GPL v3.

We would like to acknowledge the authors of GNU Wget as Wpull uses algorithms from Wget.

