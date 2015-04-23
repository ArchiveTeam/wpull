==================================
Differences between Wpull and Wget
==================================

In most cases, Wpull can be substituted with Wget easily. However, some options may not be implemented yet.


Missing in Wpull
================

* ``--background``
* ``--execute``
* ``--config``
* ``--spider``
* ``--ignore-case``
* ``--ask-password``
* ``--unlink``
* ``--method``
* ``--body-data``
* ``--body-file``
* ``--auth-no-challenge``: Temporarily on by default, but specifying the option is not yet available. Digest authentication is not yet supported.
* ``--no-passive-ftp``
* ``--mirror``
* ``--strict-comments``: No plans for support of this option.
* ``--regex-type=posix``: No plans to support posix regex.
* Features greater than Wget 1.15.


Missing in Wget
===============

* ``--python-script``
* ``--lua-script``
* ``--plugin-args``
* ``--database``
* ``--database-uri``
* ``--concurrent``
* ``--debug-console-port``
* ``--debug-manhole``
* ``--ignore-fatal-errors``
* ``--monitor-disk``
* ``--monitor-memory``
* ``--very-quiet``
* ``--ascii-print``
* ``--http-proxy``
* ``--https-proxy``
* ``--proxy-domains``
* ``--proxy-exclude-domains``
* ``--proxy-hostnames``
* ``--proxy-exclude-hostnames``
* ``--retry-dns-error``
* ``--session-timeout``
* ``--no-skip-getaddrinfo``
* ``--no-robots``
* ``--http-compression`` (gzip, deflate, & raw deflate)
* ``--html-parser``
* ``--link-extractors``
* ``--escaped-fragment``
* ``--strip-session-id``
* ``--no-strong-crypto``
* ``--no-use-internal-ca-certs``
* ``--warc-append``
* ``--warc-move``
* ``--page-requisites-level``
* ``--sitemaps``
* ``--hostnames``
* ``--exclude-hostnames``
* ``--span-hosts-allow``
* ``--no-strong-redirects``
* ``--proxy-server``
* ``--proxy-server-address``
* ``--proxy-server-port``
* ``--phantomjs``
* ``--phantomjs-exe``
* ``--phantomjs-max-time``
* ``--phantomjs-scroll``
* ``--phantomjs-wait``
* ``--no-phantomjs-snapshot``
* ``--no-phantomjs-smart-scroll``
* ``--youtube-dl``
* ``--youtube-dl-exe``
