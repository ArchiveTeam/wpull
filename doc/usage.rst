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

.. note:: When resuming downloads with ``--warc-file``, Wpull will
   overwrite the WARC file by default. You should either rename the existing
   file manually or use the additional option ``--warc-append``.


Options
=======

Wpull offers a brief overview of the options::

    python3 -m wpull --help

.. toctree::
   :maxdepth: 2

   terse_options
