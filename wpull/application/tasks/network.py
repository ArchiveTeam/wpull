import functools
import gettext
import logging
import asyncio

from wpull.backport.logging import BraceMessage as __
from wpull.network.connection import Connection, SSLConnection
from wpull.network.dns import IPFamilyPreference
from wpull.pipeline.pipeline import ItemTask
from wpull.pipeline.app import AppSession
from wpull.proxy.client import HTTPProxyConnectionPool

_logger = logging.getLogger(__name__)
_ = gettext.gettext


class NetworkSetupTask(ItemTask[AppSession]):
    @asyncio.coroutine
    def process(self, session: AppSession):
        self._build_resolver(session)
        self._build_connection_pool(session)

    @classmethod
    def _build_resolver(cls, session: AppSession):
        '''Build resolver.'''
        args = session.args
        dns_timeout = args.dns_timeout

        if args.timeout:
            dns_timeout = args.timeout

        if args.inet_family == 'IPv4':
            family = IPFamilyPreference.ipv4_only
        elif args.inet_family == 'IPv6':
            family = IPFamilyPreference.ipv6_only
        elif args.prefer_family == 'IPv6':
            family = IPFamilyPreference.prefer_ipv6
        elif args.prefer_family == 'IPv4':
            family = IPFamilyPreference.prefer_ipv4
        else:
            family = IPFamilyPreference.any

        return session.factory.new(
            'Resolver',
            family=family,
            timeout=dns_timeout,
            rotate=args.rotate_dns,
            cache=session.factory.class_map['Resolver'].new_cache() if args.dns_cache else None,
        )

    @classmethod
    def _build_connection_pool(cls, session: AppSession):
        '''Create connection pool.'''
        args = session.args
        connect_timeout = args.connect_timeout
        read_timeout = args.read_timeout

        if args.timeout:
            connect_timeout = read_timeout = args.timeout

        if args.limit_rate:
            bandwidth_limiter = session.factory.new('BandwidthLimiter',
                                                    args.limit_rate)
        else:
            bandwidth_limiter = None

        connection_factory = functools.partial(
            Connection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=session.args.bind_address,
            bandwidth_limiter=bandwidth_limiter,
        )

        ssl_connection_factory = functools.partial(
            SSLConnection,
            timeout=read_timeout,
            connect_timeout=connect_timeout,
            bind_host=session.args.bind_address,
            ssl_context=session.ssl_context,
        )

        if not session.args.no_proxy:
            if session.args.https_proxy:
                http_proxy = session.args.http_proxy.split(':', 1)
                proxy_ssl = True
            elif session.args.http_proxy:
                http_proxy = session.args.http_proxy.split(':', 1)
                proxy_ssl = False
            else:
                http_proxy = None
                proxy_ssl = None

            if http_proxy:
                http_proxy[1] = int(http_proxy[1])

                if session.args.proxy_user:
                    authentication = (session.args.proxy_user,
                                      session.args.proxy_password)
                else:
                    authentication = None

                session.factory.class_map['ConnectionPool'] = \
                    HTTPProxyConnectionPool

                host_filter = session.factory.new(
                    'ProxyHostFilter',
                    accept_domains=session.args.proxy_domains,
                    reject_domains=session.args.proxy_exclude_domains,
                    accept_hostnames=session.args.proxy_hostnames,
                    reject_hostnames=session.args.proxy_exclude_hostnames
                )

                return session.factory.new(
                    'ConnectionPool',
                    http_proxy,
                    proxy_ssl=proxy_ssl,
                    authentication=authentication,
                    resolver=session.factory['Resolver'],
                    connection_factory=connection_factory,
                    ssl_connection_factory=ssl_connection_factory,
                    host_filter=host_filter,
                )

        return session.factory.new(
            'ConnectionPool',
            resolver=session.factory['Resolver'],
            connection_factory=connection_factory,
            ssl_connection_factory=ssl_connection_factory
        )
