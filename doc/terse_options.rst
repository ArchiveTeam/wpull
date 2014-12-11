Brief Option Overview
=====================

::

  usage: __main__.py [-h] [-V] [--python-script FILE | --lua-script FILE]
                     [--database FILE | --database-uri URI] [--concurrent N]
                     [--debug-console-port PORT] [--debug-manhole]
                     [--ignore-fatal-errors] [-o FILE | -a FILE]
                     [-d | -q | -v | -nv] [--ascii-print] [-i FILE] [-F]
                     [-B URL] [--http-proxy HTTP_PROXY]
                     [--https-proxy HTTPS_PROXY] [--proxy-user USER]
                     [--proxy-password PASS] [--no-proxy]
                     [--no-secure-proxy-tunnel] [-t NUMBER]
                     [--retry-connrefused] [--retry-dns-error] [-O FILE] [-nc]
                     [-c] [--progress TYPE={bar,dot,none}] [-N]
                     [--no-use-server-timestamps] [-S] [-T SECONDS]
                     [--dns-timeout SECS] [--connect-timeout SECS]
                     [--read-timeout SECS] [-w SECONDS] [--waitretry SECONDS]
                     [--random-wait] [-Q NUMBER] [--bind-address ADDRESS]
                     [--no-dns-cache] [--rotate-dns]
                     [--restrict-file-names MODES=<ascii,lower,nocontrol,unix,upper,windows>]
                     [-4 | -6 | --prefer-family FAMILY={IPv4,IPv6}]
                     [--user USER] [--password PASSWORD] [--no-iri]
                     [--local-encoding ENC] [--remote-encoding ENC]
                     [--max-filename-length NUMBER] [-nd | -x] [-nH]
                     [--protocol-directories] [-P PREFIX] [--cut-dirs NUMBER]
                     [--http-user HTTP_USER] [--http-password HTTP_PASSWORD]
                     [--default-page NAME] [--ignore-length] [--header STRING]
                     [--max-redirect NUMBER] [--referer URL] [--save-headers]
                     [-U AGENT] [--no-robots] [--no-http-keep-alive]
                     [--no-cookies] [--load-cookies FILE] [--save-cookies FILE]
                     [--keep-session-cookies]
                     [--post-data STRING | --post-file FILE]
                     [--content-on-error] [--http-compression]
                     [--html-parser {html5lib,libxml2-lxml}]
                     [--link-extractors <css,html,javascript>]
                     [--secure-protocol PR={SSLv3,TLSv1,auto}] [--https-only]
                     [--no-check-certificate] [--certificate FILE]
                     [--certificate-type TYPE={PEM}] [--private-key FILE]
                     [--private-key-type TYPE={PEM}] [--ca-certificate FILE]
                     [--ca-directory DIR] [--no-use-internal-ca-certs]
                     [--random-file FILE] [--edg-file FILE] [--ftp-user USER]
                     [--ftp-password PASS] [--no-remove-listing]
                     [--warc-file FILENAME] [--warc-append]
                     [--warc-header STRING] [--warc-max-size NUMBER]
                     [--warc-move DIRECTORY] [--warc-cdx] [--warc-dedup FILE]
                     [--no-warc-compression] [--no-warc-digests]
                     [--no-warc-keep-log] [--warc-tempdir DIRECTORY] [-r]
                     [-l NUMBER] [--delete-after] [-k] [-K] [-p] [--sitemaps]
                     [-A LIST] [-R LIST] [--accept-regex REGEX]
                     [--reject-regex REGEX] [--regex-type TYPE={posix}]
                     [-D LIST] [--exclude-domains LIST] [--hostnames LIST]
                     [--exclude-hostnames LIST] [--follow-ftp]
                     [--follow-tags LIST] [--ignore-tags LIST]
                     [-H | --span-hosts-allow LIST=<linked-pages,page-requisites>]
                     [-L] [-I LIST] [-X LIST] [-np] [--no-strong-redirects]
                     [--phantomjs] [--phantomjs-exe PATH]
                     [--phantomjs-scroll NUM] [--phantomjs-wait SEC]
                     [--no-phantomjs-snapshot] [--no-phantomjs-smart-scroll]
                     [URL [URL ...]]

  Wget-compatible web downloader and crawler.

  positional arguments:
    URL                   the URL to be downloaded

  optional arguments:
    -h, --help            show this help message and exit

  startup:
    -V, --version         show program's version number and exit
    --python-script FILE  load Python hook script from FILE
    --lua-script FILE     load Lua hook script from FILE
    --database FILE       save database tables into FILE instead of memory
                          (default: :memory:)
    --database-uri URI    save database tables at SQLAlchemy URI instead of
                          memory
    --concurrent N        run at most N downloads at the same time (default: 1)
    --debug-console-port PORT
                          run a web debug console at given port number
    --debug-manhole       install Manhole debugging socket
    --ignore-fatal-errors
                          ignore all internal fatal exception errors

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
                          download URLs listed in FILE
    -F, --force-html      read URL input files as HTML files
    -B URL, --base URL    resolves input relative URLs to URL

  proxy:
    --http-proxy HTTP_PROXY
                          HTTP proxy for HTTP requests
    --https-proxy HTTPS_PROXY
                          HTTP proxy for HTTPS requests
    --proxy-user USER     username for proxy "basic" authentication
    --proxy-password PASS
                          password for proxy "basic" authentication
    --no-proxy            disable proxy support
    --no-secure-proxy-tunnel
                          disable use of encryption when using proxy

  download:
    -t NUMBER, --tries NUMBER
                          try NUMBER of times on transient errors (default: 20)
    --retry-connrefused   retry even if the server does not accept connections
    --retry-dns-error     retry even if DNS fails to resolve hostname
    -O FILE, --output-document FILE
                          stream every document into FILE
    -nc, --no-clobber     don’t use anti-clobbering filenames
    -c, --continue        resume downloading a partially-downloaded file
    --progress TYPE={bar,dot,none}
                          choose the type of progress indicator (default: bar)
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
                          (default: 900)
    -w SECONDS, --wait SECONDS
                          wait SECONDS seconds between requests
    --waitretry SECONDS   wait up to SECONDS seconds on retries (default: 10.0)
    --random-wait         randomly perturb the time between requests
    -Q NUMBER, --quota NUMBER
                          stop after downloading NUMBER bytes
    --bind-address ADDRESS
                          bind to ADDRESS on the local host
    --no-dns-cache        disable caching of DNS lookups
    --rotate-dns          use different resolved IP addresses on requests
    --restrict-file-names MODES=<ascii,lower,nocontrol,unix,upper,windows>
                          list of safe filename modes to use (default: ['unix'])
    -4, --inet4-only      connect to IPv4 addresses only
    -6, --inet6-only      connect to IPv6 addresses only
    --prefer-family FAMILY={IPv4,IPv6}
                          prefer to connect to FAMILY IP addresses
    --user USER           username for both FTP and HTTP authentication
    --password PASSWORD   password for both FTP and HTTP authentication
    --no-iri              use ASCII encoding only
    --local-encoding ENC  use ENC as the encoding of input files and options
    --remote-encoding ENC
                          force decoding documents using codec ENC
    --max-filename-length NUMBER
                          limit filename length to NUMBER characters (default:
                          160)

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
                          save everything under the directory PREFIX (default:
                          .)
    --cut-dirs NUMBER     don’t make NUMBER of leading directories

  HTTP:
    --http-user HTTP_USER
                          username for HTTP authentication
    --http-password HTTP_PASSWORD
                          password for HTTP authentication
    --default-page NAME   use NAME as index page if not known (default:
                          index.html)
    --ignore-length       ignore any Content-Length provided by the server
    --header STRING       adds STRING to the HTTP header
    --max-redirect NUMBER
                          follow only up to NUMBER document redirects (default:
                          20)
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
    --content-on-error    keep error pages
    --http-compression    request servers to use HTTP compression
    --html-parser {html5lib,libxml2-lxml}
                          select HTML parsing library and strategy (default:
                          html5lib)
    --link-extractors <css,html,javascript>
                          specify which link extractors to use (default:
                          ['html', 'css', 'javascript'])

  SSL:
    --secure-protocol PR={SSLv3,TLSv1,auto}
                          specify the version of the SSL protocol to use
                          (default: auto)
    --https-only          download only HTTPS URLs
    --no-check-certificate
                          don’t validate SSL server certificates
    --certificate FILE    use FILE containing the local client certificate
    --certificate-type TYPE={PEM}
    --private-key FILE    use FILE containing the local client private key
    --private-key-type TYPE={PEM}
    --ca-certificate FILE
                          load and use CA certificate bundle from FILE (default:
                          /etc/ssl/certs/ca-certificates.crt)
    --ca-directory DIR    load and use CA certificates from DIR (default:
                          /etc/ssl/certs/)
    --no-use-internal-ca-certs
                          don’t use CA certificates included with Wpull
    --random-file FILE    use data from FILE to seed the SSL PRNG
    --edg-file FILE       connect to entropy gathering daemon using socket FILE

  FTP:
    --ftp-user USER       username for FTP login
    --ftp-password PASS   password for FTP login
    --no-remove-listing   keep directory file listings

  WARC:
    --warc-file FILENAME  save WARC file to filename prefixed with FILENAME
    --warc-append         append instead of overwrite the output WARC file
    --warc-header STRING  include STRING in WARC file metadata
    --warc-max-size NUMBER
                          write sequential WARC files sized about NUMBER bytes
    --warc-move DIRECTORY
                          move WARC files to DIRECTORY as they complete
    --warc-cdx            write CDX file along with the WARC file
    --warc-dedup FILE     write revisit records using digests in FILE
    --no-warc-compression
                          do not compress the WARC file
    --no-warc-digests     do not compute and save SHA1 hash digests
    --no-warc-keep-log    do not save a log into the WARC file
    --warc-tempdir DIRECTORY
                          use temporary DIRECTORY for preparing WARC files
                          (default: .)

  recursion:
    -r, --recursive       follow links and download them
    -l NUMBER, --level NUMBER
                          limit recursion depth to NUMBER (default: 5)
    --delete-after        download files temporarily and delete them after
    -k, --convert-links   rewrite links in files that point to local files
    -K, --backup-converted
                          save original files before converting their links
    -p, --page-requisites
                          download objects embedded in pages
    --sitemaps            download Sitemaps to discover more links

  filters:
    -A LIST, --accept LIST
                          download only files with suffix in LIST
    -R LIST, --reject LIST
                          don’t download files with suffix in LIST
    --accept-regex REGEX  download only URLs matching REGEX
    --reject-regex REGEX  don’t download URLs matching REGEX
    --regex-type TYPE={posix}
                          use regex TYPE
    -D LIST, --domains LIST
                          download only from LIST of hostname suffixes
    --exclude-domains LIST
                          don’t download from LIST of hostname suffixes
    --hostnames LIST      download only from LIST of hostnames
    --exclude-hostnames LIST
                          don’t download from LIST of hostnames
    --follow-ftp          follow links to FTP sites
    --follow-tags LIST    follow only links contained in LIST of HTML tags
    --ignore-tags LIST    don’t follow links contained in LIST of HTML tags
    -H, --span-hosts      follow links and page requisites to other hostnames
    --span-hosts-allow LIST=<linked-pages,page-requisites>
                          selectively span hosts for resource types in LIST
    -L, --relative        follow only relative links
    -I LIST, --include-directories LIST
                          download only paths in LIST
    -X LIST, --exclude-directories LIST
                          don’t download paths in LIST
    -np, --no-parent      don’t follow to parent directories on URL path
    --no-strong-redirects
                          don’t implicitly allow span hosts for redirects

  PhantomJS:
    --phantomjs           use PhantomJS for loading dynamic pages
    --phantomjs-exe PATH  path of PhantomJS executable (default: phantomjs)
    --phantomjs-scroll NUM
                          scroll the page up to NUM times (default: 10)
    --phantomjs-wait SEC  wait SEC seconds between page interactions (default:
                          1.0)
    --no-phantomjs-snapshot
                          don’t take dynamic page snapshots
    --no-phantomjs-smart-scroll
                          always scroll the page to maximum scroll count option

