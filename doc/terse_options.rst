Brief Option Overview
=====================

::

  usage: __main__.py [-h] [-V] [--python-script FILE | --lua-script FILE]
                     [--database FILE] [--concurrent N] [-o FILE | -a FILE]
                     [-d | -q | -v | -nv] [--ascii-print] [-i FILE] [-t NUMBER]
                     [--retry-connrefused] [--retry-dns-error] [-nc] [-c]
                     [--progress TYPE] [-N] [--no-use-server-timestamps] [-S]
                     [-T SECONDS] [--dns-timeout SECS] [--connect-timeout SECS]
                     [--read-timeout SECS] [-w SECONDS] [--waitretry SECONDS]
                     [--random-wait] [--bind-address ADDRESS] [--rotate-dns]
                     [-4 | -6 | --prefer-family FAMILY] [-nd | -x] [-nH]
                     [--protocol-directories] [-P PREFIX] [--cut-dirs NUMBER]
                     [--default-page NAME] [--header STRING]
                     [--max-redirect NUMBER] [--referer URL] [--save-headers]
                     [-U AGENT] [--no-robots] [--no-http-keep-alive]
                     [--no-cookies] [--load-cookies FILE] [--save-cookies FILE]
                     [--keep-session-cookies]
                     [--post-data STRING | --post-file FILE]
                     [--secure-protocol PR] [--no-check-certificate]
                     [--certificate FILE] [--certificate-type TYPE]
                     [--private-key FILE] [--private-key-type TYPE]
                     [--ca-certificate FILE] [--ca-directory DIR]
                     [--no-use-internal-ca-certs] [--random-file FILE]
                     [--edg-file FILE] [--warc-file FILENAME] [--warc-append]
                     [--warc-header STRING] [--warc-cdx] [--no-warc-compression]
                     [--no-warc-digests] [--no-warc-keep-log]
                     [--warc-tempdir DIRECTORY] [-r] [-l NUMBER]
                     [--delete-after] [-k] [-K] [-p] [--accept-regex REGEX]
                     [--reject-regex REGEX] [--regex-type TYPE] [-D LIST]
                     [--exclude-domains LIST] [--hostnames LIST]
                     [--exclude-hostnames LIST] [--follow-tags LIST]
                     [--ignore-tags LIST] [-H] [-L] [-I LIST] [-X LIST] [-np]
                     [URL [URL ...]]

  Wget-compatible web downloader.

  positional arguments:
    URL                   the URL to be downloaded

  optional arguments:
    -h, --help            show this help message and exit

  startup:
    -V, --version         show program's version number and exit
    --python-script FILE  load Python hook script from FILE
    --lua-script FILE     load Lua hook script from FILE
    --database FILE       save database tables into FILE instead of memory
    --concurrent N        run at most N downloads at the same time

  logging and input:
    -o FILE, --output-file FILE
                          write program messages to FILE
    -a FILE, --append-output FILE
                          append program messages to FILE
    -d, --debug           print debugging messages
    -q, --quiet           do not print program messages
    -v, --verbose         print informative program messages
    -nv, --no-verbose     print program warning and informative messages only
    --ascii-print         print program messages in ASCII only
    -i FILE, --input-file FILE
                          download URLs listen from FILE

  download:
    -t NUMBER, --tries NUMBER
                          try NUMBER of times on transient errors
    --retry-connrefused   retry even if the server does not accept connections
    --retry-dns-error     retry even if DNS fails to resolve hostname
    -nc, --no-clobber     don’t use anti-clobbering filenames
    -c, --continue        resume downloading a partially-downloaded file
    --progress TYPE       choose the type of progress indicator
    -N, --timestamping    only download files that are newer than local files
    --no-use-server-timestamps
                          don’t set the last-modified time on files
    -S, --server-response
                          print the protocol responses from the server
    -T SECONDS, --timeout SECONDS
                          set all timeout options to SECONDS
    --dns-timeout SECS    timeout after SECS seconds for DNS requests
    --connect-timeout SECS
                          timeout after SECS seconds for connection requests
    --read-timeout SECS   timeout after SECS seconds for reading requests
    -w SECONDS, --wait SECONDS
                          wait SECONDS seconds between requests
    --waitretry SECONDS   wait up to SECONDS seconds on retries
    --random-wait         randomly perturb the time between requests
    --bind-address ADDRESS
                          bind to ADDRESS on the local host
    --rotate-dns          use different resolved IP addresses on requests
    -4, --inet4-only      connect to IPv4 addresses only
    -6, --inet6-only      connect to IPv6 addresses only
    --prefer-family FAMILY
                          prefer to connect to FAMILY IP addresses

  directories:
    -nd, --no-directories
                          don’t create directories
    -x, --force-directories
                          always create directories
    -nH, --no-host-directories
                          don’t create directories for hostnames
    --protocol-directories
                          create directories for URL schemes
    -P PREFIX, --directory-prefix PREFIX
                          save everything under the directory PREFIX
    --cut-dirs NUMBER     don’t make NUMBER of leading directories

  HTTP:
    --default-page NAME   use NAME as index page if not known
    --header STRING       adds STRING to the HTTP header
    --max-redirect NUMBER
                          follow only up to NUMBER document redirects
    --referer URL         always use URL as the referrer
    --save-headers        include server header responses in files
    -U AGENT, --user-agent AGENT
                          use AGENT instead of Wpull’s user agent
    --no-robots           ignore robots.txt directives
    --no-http-keep-alive  disable persistent HTTP connections
    --no-cookies          disables HTTP cookie support
    --load-cookies FILE   load Mozilla cookies.txt from FILE
    --save-cookies FILE   save Mozilla cookies.txt to FILE
    --keep-session-cookies
                          include session cookies when saving cookies to file
    --post-data STRING    use POST for all requests with query STRING
    --post-file FILE      use POST for all requests with query in FILE

  SSL:
    --secure-protocol PR  specifiy the version of the SSL protocol to use
    --no-check-certificate
                          don’t validate SSL server certificates
    --certificate FILE    use FILE containing the local client certificate
    --certificate-type TYPE
    --private-key FILE    use FILE containing the local client private key
    --private-key-type TYPE
    --ca-certificate FILE
                          load and use CA certificate bundle from FILE
    --ca-directory DIR    load and use CA certificates from DIR
    --no-use-internal-ca-certs
                          don’t use CA certificates included with Wpull
    --random-file FILE    use data from FILE to seed the SSL PRNG
    --edg-file FILE       connect to entropy gathering daemon using socket FILE

  WARC:
    --warc-file FILENAME  save WARC file to filename prefixed with FILENAME
    --warc-append         append instead of overwrite the output WARC file
    --warc-header STRING  include STRING in WARC file metadata
    --warc-cdx            write CDX file along with the WARC file
    --no-warc-compression
                          do not compress the WARC file
    --no-warc-digests     do not compute and save SHA1 hash digests
    --no-warc-keep-log    do not save a log into the WARC file
    --warc-tempdir DIRECTORY
                          use temporary DIRECTORY for preparing WARC files

  recursion:
    -r, --recursive       follow links and download them
    -l NUMBER, --level NUMBER
                          limit recursion depth to NUMBER
    --delete-after        download files temporarily and delete them after
    -k, --convert-links   rewrite links in files that point to local files
    -K, --backup-converted
                          save original files before converting their links
    -p, --page-requisites
                          download objects embedded in pages

  filters:
    --accept-regex REGEX  download only URLs matching REGEX
    --reject-regex REGEX  don’t download URLs matching REGEX
    --regex-type TYPE     use regex TYPE
    -D LIST, --domains LIST
                          download only from LIST of hostname suffixes
    --exclude-domains LIST
                          don’t download from LIST of hostname suffixes
    --hostnames LIST      download only from LIST of hostnames
    --exclude-hostnames LIST
                          don’t download from LIST of hostnames
    --follow-tags LIST    follow only links contained in LIST of HTML tags
    --ignore-tags LIST    don’t follow links contained in LIST of HTML tags
    -H, --span-hosts      follow links to other hostnames
    -L, --relative        follow only relative links
    -I LIST, --include-directories LIST
                          download only paths in LIST
    -X LIST, --exclude-directories LIST
                          don’t download paths in LIST
    -np, --no-parent      don’t follow to parent directories on URL path

