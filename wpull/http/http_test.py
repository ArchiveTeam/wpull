# encoding=utf-8
import functools
import os.path
import socket
import ssl
import sys
import tornado.testing
import tornado.web

from wpull.backport.testing import unittest
from wpull.errors import (ConnectionRefused, SSLVerficationError, NetworkError,
                          ProtocolError, NetworkTimedOut)
from wpull.http.client import Client
from wpull.http.connection import (Connection, ConnectionPool,
                                   HostConnectionPool, ConnectionParams)
from wpull.http.request import Request, Response
from wpull.http.util import parse_charset
from wpull.recorder import DebugPrintRecorder
from wpull.testing.badapp import BadAppTestCase


DEFAULT_TIMEOUT = 30


class TestClient(BadAppTestCase):
    def setUp(self):
        super().setUp()
        tornado.ioloop.IOLoop.current().set_blocking_log_threshold(0.5)

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_min(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)

        for dummy in range(2):
            response = yield client.fetch(
                Request.new(self.get_url('/sleep_short')))
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(1, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_max(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/sleep_short'))) for dummy in range(6)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(6, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_over_max(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/sleep_short'))) for dummy in range(12)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)
            self.assertEqual(b'12', response.body.content)

        self.assertEqual(1, len(connection_pool))
        connection_pool_entry = list(connection_pool.values())[0]
        self.assertIsInstance(connection_pool_entry, HostConnectionPool)
        self.assertEqual(6, len(connection_pool_entry))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_connection_pool_clean(self):
        connection_pool = ConnectionPool()
        client = Client(connection_pool)
        requests = [client.fetch(
            Request.new(self.get_url('/'))) for dummy in range(12)]
        responses = yield requests

        for response in responses:
            self.assertEqual(200, response.status_code)

        connection_pool.clean()

        self.assertEqual(0, len(connection_pool))

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_throw(self):
        client = Client()

        try:
            yield client.fetch(Request.new('http://wpull-no-exist.invalid'))
        except NetworkError:
            pass
        else:
            self.fail()

    @tornado.testing.gen_test(timeout=DEFAULT_TIMEOUT)
    def test_client_exception_recovery(self):
        connection_factory = functools.partial(
            Connection, params=ConnectionParams(read_timeout=0.2)
        )
        host_connection_pool_factory = functools.partial(
            HostConnectionPool, connection_factory=connection_factory)
        connection_pool = ConnectionPool(host_connection_pool_factory)
        client = Client(connection_pool)

        for dummy in range(7):
            try:
                yield client.fetch(
                    Request.new(self.get_url('/header_early_close')),
                    recorder=DebugPrintRecorder()
                )
            except NetworkError:
                pass
            else:
                self.fail()

        for dummy in range(7):
            response = yield client.fetch(Request.new(self.get_url('/')))
            self.assertEqual(200, response.status_code)
