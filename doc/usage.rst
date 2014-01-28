=====
Usage
=====


Intro
=====

Wpull is a command line oriented program much like Wget. After all, Wpull
is intended to be (almost) a drop-in replacement for Wget. If you are not
familiar with Wget, please see the `Wikipedia article on Wget
<https://en.wikipedia.org/wiki/Wget>`_.


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


Options
=======

Wpull offers a brief overview of the options::

    python3 -m wpull --help

