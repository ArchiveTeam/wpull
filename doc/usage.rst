=====
Usage
=====


Intro
=====

Wpull is a command line oriented program much like Wget. It is
non-interactive and requires all options to specified on start up. If
you are not familiar with Wget, please see the `Wikipedia article on
Wget <https://en.wikipedia.org/wiki/Wget>`_.



Examples
========

.. ⬇ Please keep these examples in sync with the README file. ⬇

To download the About page of Google.com::

    wpull google.com/about

To archive a website::

    wpull billy.blogsite.example --warc-file blogsite-billy \
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


Wpull can also be invoked using::

    python3 -m wpull


Stopping & Resuming
===================

To gracefully stop Wpull, press CTRL+C (or send SIGINT). Wpull will quit
once the current download has finished. To stop immediately, press CTRL+C
again (or send SIGTERM).

If you have used the ``--database`` option, Wpull can reuse the
existing database for resuming crawls. This behavior is different than
``--continue``. Resuming with ``--continue`` is intended for resuming
partially downloaded files while ``--database`` is intended for resuming
partial crawls.

Be sure to include the original options from the previous run if you want
the same behavior as the previous run.

.. note:: When resuming downloads with ``--warc-file``, Wpull will
   overwrite the WARC file by default. You should either rename the existing
   file manually or use the additional option ``--warc-append``.


PhantomJS Integration (Experimental)
====================================

``--phantomjs`` will enable PhantomJS integration. If a HTML document is encountered, Wpull will open the URL in PhantomJS. The requests will go through an HTTP proxy to Wpull's HTTP client (which can be recorded with ``--warc-file``).

After the page is loaded, Wpull will try to scroll the page as specified by ``--phantomjs-scroll``. Then, the HTML source is scraped for URLs as normal. HTML and PDF snapshots are taken by default.

Currently, Wpull will *not do anything else* to manipulate the page such as clicking on links. As a consequence, Wpull with PhantomJS is *not* a complete solution for dynamic web pages yet!

The filename of the PhantomJS executable must be on the PATH environment variable.

.. warning:: Wpull communicates insecurely with PhantomJS on localhost with TCP sockets.

    It is possible for another user, on the same machine as Wpull, to send bogus requests to the HTTP proxy or RPC server. Wpull, however, does *not* expose the HTTP proxy or PRC server outside to the net.


Options
=======

Wpull offers a brief overview of the options::

    wpull --help

.. toctree::
   :maxdepth: 2

   terse_options
