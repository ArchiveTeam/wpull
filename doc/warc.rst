WARC Specification
==================

Additional de-facto and custom extensions to the WARC standard.


FTP
+++

FTP recording follows `Heritrix specifications <http://aaron.blog.archive.org/2013/05/17/handling-archived-ftp-resources/>`_.


Control Conversation
--------------------

The Control Conversation is recorded as

* WARC-Type: ``metadata``
* Content-Type: ``text/x-ftp-control-conversation``
* WARC-Target-URI: a URL. For example, ``ftp://anonymous@example.com/treasure.txt``
* WARC-IP-Address: an IPv4 address with port or an IPv6 address with brackets and port

The resource is formatted as followed:

* Events are indented with an ASCII asterisk and space.
* Requests are indented with an ASCII greater-than and space.
* Responses are indented with an ASCII less-than and space.

The document encoding is Latin-1.


Response data
-------------

The response data is recorded as

* WARC-Type: ``resource``
* WARC-Target-URI: a URL. For example, ``ftp://anonymous@example.com/treasure.txt``
* WARC-Concurrent-To: a WARC Record ID of the Control Conversation


PhantomJS
+++++++++


Snapshot
--------

A PhantomJS Snapshot represents the state of the DOM at the time of capture.

A Snapshot is recorded as

* WARC-Type: ``resource``
* WARC-Target-URI: ``urn:X-wpull:snapshot?url=URLHERE`` where ``URLHERE`` is a percent-encoded URL of the PhantomJS page.
* Content-Type: one of ``application/pdf``, ``text/html``, ``image/png``
* WARC-Concurrent-To: a WARC Record ID of a Snapshot Action Metadata.


Snapshot Action Metadata
------------------------

An Action Metadata is a log of steps performed before a Snapshot is taken.

It is recorded as

* WARC-Type: ``metadata``
* Content-Type: ``application/json``
* WARC-Target-URI: ``urn:X-wpull:snapshot?url=URLHERE`` where ``URLHERE`` is a percent-encoded URL of the PhantomJS page.


Wpull Metadata
++++++++++++++

Log
---

Wpull's log is recorded as

* WARC-Type: ``resource``
* Content-Type: ``text/plain``
* WARC-Target-URI: ``urn:X-wpull:log``

The document encoding is UTF-8.


