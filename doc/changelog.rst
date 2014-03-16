==========
What's New
==========

0.26 (2014-03-16)
==================

* Fixes crash when URLs like ``http://example.com]`` were encountered.
* Implements ``--sitemaps``.
* Implements ``--max-filename-length``.
* Implements ``--span-hosts-allow`` (experimental, see issues #61, #66).
* Query strings items like ``?a&b`` are now preserved and no longer normalized to ``?a=&b=``.
* API:

  * url.URLInfo.normalize() was removed since it was mainly used internally.
  * Added url.normalize() convenience function.
  * writer: safe_filename(), url_to_filename(), url_to_dir_path() were modified.


0.25 (2014-03-13)
=================

* Fixes link converter not operating on the correct files when ``.N`` files were written.
* Fixes apparent hang when Wpull is almost finished on documents with many links.

  * Previously, Wpull adds all URLs to the database causing overhead processing to be done in the database. Now, only requisite URLs are added to the database.

* Implements ``--restrict-file-names``.
* Implements ``--quota``.
* Implements ``--warc-max-size``. Like Wget, "max size" is not the maximum size of each WARC file but it is the threshold size to trigger a new file. Unlike Wget, ``request`` and ``response`` records are not split across WARC files.
* Implements ``--content-on-error``.
* Supports recording scrolling actions in WARC file when PhantomJS is enabled.
* Adds the ``wpull`` command to ``bin/``.
* Database schema change: ``filename`` column was added.
* API:

  * converter.py: Converters no longer use PathNamer.
  * writer.py: ``sanitize_file_parts()`` was removed in favor of new ``safe_filename()``. ``save_document()`` returns a filename.
  * WebProcessor now requires a root path to be specified.
  * WebProcessor initializer now takes "parameter objects".

* Install requires new dependency: ``namedlist``.


0.24 (2014-03-09)
==================

* Fixes crash when document encoding could not be detected. Thanks to DopefishJustin for reporting.
* Fixes non-index files incorrectly saved where an extra directory was added as part of their path.
* URL path escaping is relaxed. This helps with servers that don't handle percent-encoding correctly.
* ``robots.txt`` now bypasses the filters. Use ``--no-strong-robots`` to disable this behavior.
* Redirects implicitly span hosts. Use ``--no-strong-redirects`` to disable this behavior.
* Scripting: ``should_fetch()`` info dict now contains ``reason`` as a key.


0.23.1 (2014-03-07)
===================

* Important: Fixes issue where URLs were downloaded repeatedly.


0.23 (2014-03-07)
=================

* Fixes incorrect logic in fetching robots.txt when it redirects to another URL.
* Fixes port number not included in the HTTP Host header.
* Fixes occasional ``RuntimeError`` when pressing CTRL+C.
* Fixes fetching URL paths containing dot segments. They are now resolved appropriately.
* Fixes ASCII progress bar not showing 100% when finished download occasionally.
* Fixes crash and improves handling of unusual document encodings and settings.
* Improves handling of links with newlines and whitespace intermixed.
* Requires beautifulsoup4 as a dependency.
* API:

  * ``util.detect_encoding()`` arguments modified to accept only a single fallback and to accept ``is_html``.
  * ``document.get_encoding()`` accepts ``is_html`` and ``peek`` arguments.


0.22.5 (2014-03-05)
===================

* The 'Refresh' HTTP header is now scraped for URLs.
* When an error occurs during writing WARC files, the WARC file is truncated back to the last good state before crashing.
* Works around error "Reached maximum read buffer size" downloading on fast connections. Side effect is intensive CPU usage.


0.22.4 (2014-03-05)
===================

* Fixes occasional error on chunked transfer encoding. Thanks to ivan for reporting.
* Fixes handling links with newlines found in HTML pages. Newlines are now stripped in links when scraping pages to better handle HTML soup.


0.22.3 (2014-03-02)
===================

* Fixes another case of ``AssertionError`` on ``url_item.is_processed`` when robots.txt was enabled.
* Fixes crash if a malformed gzip response was received.
* Fixes ``--span-hosts`` to be implicitly enabled (as with ``--no-robots``) if ``--recursive`` is not supplied. This behavior unconditionally allows downloading a single file without specifying any options. It is what a user intuitively expects.


0.22.2 (2014-03-01)
===================

* Improves performance on database operations. CPU usage should be less intensive.


0.22.1 (2014-02-28)
===================

* Fixes handling of "204 No Content" responses.
* Fixes ``AssertionError`` on ``url_item.is_processed`` when robots.txt was enabled.
* Fixes PhantomJS page scrolling to be consistent.
* Lengthens PhantomJS viewport to ensure lazy-load images are properly triggered.
* Lengthens PhantomJS paper size to reduce excessive fragmentation of blocks.


0.22 (2014-02-27)
=================

* Implements ``--phantomjs-scroll`` and ``--phantomjs-wait``.
* Implements saving HTML and PDF snapshots (including inside WARC file). Disable with ``--no-phantomjs-snapshot``.
* API: Adds PhantomJSController.


0.21.1 (2014-02-27)
===================

* Fixes missing dependencies and files in ``setup.py``.
* For PhantomJS:

  * Fixes capturing HTTPS connections .
  * Fixes statistics counter.
  * Supports very basic scraping of HTML. See Usage section.


0.21 (2014-02-26)
=================

* Fixes Request factory not used. This resolves issues where the User Agent was not set.
* Experimental PhantomJS support. It can be enabled with ``--phantomjs``. See the Usage section in the documentation for more details.
* API changes:

  * The ``http`` module was split up into smaller modules: ``http.client``, ``http.connection``, ``http.request``, ``http.util``.
  * ``ChunkedTransferStreamReader`` was added as a reusable abstraction.
  * The ``web`` module was moved to ``http.web``.
  * Added ``proxy`` module.
  * Added ``phantomjs`` module.


0.20 (2014-02-22)
=================

* Implements ``--no-dns-cache``, ``--accept``, ``--reject``.
* Scripting: Fixes ``AttributeError`` crash on ``handle_error``.
* Another possible fix for issue #27.


0.19.2 (2014-02-18)
===================

* Fixes crash if a non-HTTP URL was found during download.
* Lua scripting: Fixes booleans, coming from Wpull, mistakenly converted to integers on Python 2


0.19.1 (2014-02-14)
===================

* Fixes ``--timestamping`` functionality.
* Fixes ``--timestamping`` not checking ``.orig`` files.
* Fixes HTTP handling of responses which do not return content.


0.19 (2014-02-12)
=================

* Fixes files not actually being written.
* Implements ``--convert-links`` and ``--backup-converted``.
* API: ``HTMLScraper`` functions were refactored to be class methods. ``ScrapedLink`` was renamed to ``LinkInfo``.


0.18.1 (2014-02-11)
===================

* Fixes error when WARC but not CDX option is specified.
* Fixes closing of the SQLite database to avoid leaving temporary database files.


0.18 (2014-02-11)
==================

* Implements ``--no-warc-digests``, ``--warc-cdx``.
* Improvements on reducing CPU usage consumption.
* API: Engine and Processor interaction refactored to be asynchronous.

  * The Engine and Processor classes were modified significantly.
  * The Engine no longer is concerned with fetching requests.
  * Requests are handled within Processors. This will benefit future Processors to allow them to make arbitrary requests during processing.
  * The ``RedirectTracker`` was moved to a new ``web`` module.
  * A ``RichClient`` is implemented. It handles robots.txt, cookies, and redirect concerns.
  * ``WARCRecord`` was moved into a new ``warc`` module.


0.17.3 (2014-02-07)
===================

* Fixes ca-bundle file missing during install.
* Fixes AttributeError on ``retry_dns_error``.


0.17.2 (2014-02-06)
===================

* Another attempt to possibly fix #27.
* Implements cleaning inactive connections from the connection pool.


0.17.1 (2014-02-05)
===================

* Another attempt to possibly fix #27.
* API: Refactored ``ConnectionPool``. It now calls ``put`` on ``HostConnectionPool`` to avoid sharing a queue.


0.17 (2014-02-05)
=================

* Implements cookie support.
* Fixes non-recursive downloads where robots.txt was checked unnecessarily.
* Possibly fix issue #27 where HTTP workers get stuck.


0.16.1 (2014-02-05)
===================

* Adds some documentation about stopping Wpull and a list of all options.
* API: ``Builder`` now exposes ``Factory``.
* API: ``WebProcessorSession`` was refactored to not pass arguments through the initializer. It also now uses ``DemuxDocumentScraper`` and ``DemuxURLFilter``.


0.16 (2014-02-04)
=================

* Implements all the SSL options: ``--certificate``, ``--random-file``, ``--egd-file``, ``--secure-protocol``.
* Further improvement on database performance.


0.15.2 (2014-02-03)
===================

* Improves database performance on reducing CPU usage.


0.15.1 (2014-02-03)
===================

* Improves database performance on reducing disk reading.


0.15 (2014-02-02)
=================

* Fixes robots.txt being fetched for every request.
* Scripts: Supports ``replace`` as part of ``get_urls()``.
* Schema change: The database URL strings are normalized into a separate table. Using ``--database`` should now consume less disk space.


0.14.1 (2014-02-02)
===================

* NameValueRecord now supports a ``normalize_override`` argument to how specific keys are cased instead of the default title-case.
* Fixes WARC file's field names to match the same cases as hanzo's warc-tools. warc-tools does not support case-insensitivity as required by the WARC specification in section 4. The WARC files generated by Wpull are conformant however.


0.14 (2014-02-01)
=================

* Database change: SQLAlchemy is now used for the URL Table.

  * Scripts: ``url_info['inline']`` now returns a boolean, not an integer.

* Implements ``--post-data`` and ``--post-file``.
* Scripts can now return ``post_data`` and ``link_type`` as part of ``get_urls()``.


0.13 (2014-01-31)
=================

* Supports reading HTTP responses with gzip content type.


0.12 (2014-01-31)
=================

* No changes to program usage itself.
* More documentation.
* Major API changes due to refactoring:

  * ``http.Body`` moved to ``conversation.Body``
  * ``document.HTTPScraper``, ``document.CSSScraper`` moved to ``scraper`` module.
  * ``conversation`` module now contains base classes for protocol elements.
  * ``processor.WebProcessorSession`` now uses keyword arguments
  * ``engine.Engine`` requires ``Statistics`` argument.


0.11 (2014-01-29)
=================

* Implements ``--progress`` which includes a progress bar indicator.
* Bumps up the HTTP connection buffer size to support fast connections.


0.10.9 (2014-01-28)
===================

* Adds documentation. No program changes.


0.10.8 (2014-01-26)
===================

* Improves robustness against bad HTTP protocol messages.
* Fixes various URL and IRI handling issues.
* Fixes ``--input-file`` to work as expected.
* Fixes command line arguments not working under Python 2.


0.10 (2014-01-23)
=================

* Improves handling on URLs and document encodings.
* Implements ``--ascii-print``.
* Fixes Lua scripting conversion of Python to Lua object types.


0.9 (2014-01-21)
================

* Adds basic SSL options.


0.8 (2014-01-21)
================

* Supports Python and Lua scripting via ``--python-script`` and
  ``--lua-script``.


0.7 (2014-01-18)
================

* Fixes robots.txt support.


0.6 (2014-01-17)
================

* Implements ``--warc-append``, ``--concurrent``.
* ``--read-timeout`` default is 900 seconds.


0.5 (2014-01-17)
================

* Implements ``--no-http-keepalive``, ``--rotate-dns``.
* Adds basic support for HTTPS.


0.4 (2014-01-15)
================

* Implements ``--continue``, ``--no-clobber``, ``--timestamping``.


0.3.2 (2014-01-07)
==================

* Fixes database rows not saved correctly.


0.3 (2014-01-07)
================

* Implements ``--hostnames`` and ``--exclude-hostnames``.


0.2 (2014-01-06)
================

* Implements ``--header`` option.
* Various 3to2 bug fixes.


0.1 (2014-01-05)
================

* The first usable release.



