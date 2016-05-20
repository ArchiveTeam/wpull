import argparse
import unittest

from wpull.application.hook import Actions
from wpull.pipeline.app import AppSession
from wpull.pipeline.item import URLRecord
from wpull.pipeline.session import ItemSession
from wpull.processor.rule import ProcessingRule, FetchRule, ResultRule
from wpull.protocol.abstract.request import BaseRequest
from wpull.url import URLInfo
from wpull.urlfilter import DemuxURLFilter, SchemeFilter


class TestFetchRule(unittest.TestCase):
    def get_fetch_rule(self):
        url_filter = DemuxURLFilter([SchemeFilter()])
        return FetchRule(url_filter=url_filter)

    def test_consult_helix_fossil(self):
        fetch_rule = self.get_fetch_rule()
        fetch_rule.consult_helix_fossil()

    def test_consult_filters(self):
        fetch_rule = self.get_fetch_rule()

        url_info = URLInfo.parse('http://example.com')
        url_record = new_mock_url_record()

        verdict, reason, test_info = fetch_rule.consult_filters(url_info, url_record)

        self.assertTrue(verdict)
        self.assertEqual('filters', reason)

    def test_is_only_span_hosts_failed(self):
        info = {
            'verdict': True,
            'passed': ('SpanHostsFilter', 'SchemeFilter'),
            'failed': (),
            'map': {
                'SpanHostsFilter': True,
                'SchemeFilter': True
            },
        }

        self.assertFalse(FetchRule.is_only_span_hosts_failed(info))

        info = {
            'verdict': False,
            'passed': ('SchemeFilter',),
            'failed': ('SpanHostsFilter',),
            'map': {
                'SpanHostsFilter': False,
                'SchemeFilter': True
            },
        }

        self.assertTrue(FetchRule.is_only_span_hosts_failed(info))


class TestResultRule(unittest.TestCase):
    def get_result_rule(self):
        return ResultRule()

    def test_handle_response(self):
        result_rule = self.get_result_rule()
        item_session = new_mock_item_session()

        action = result_rule.handle_response(item_session)

        self.assertEqual(Actions.NORMAL, action)


class TestProcessingRule(unittest.TestCase):
    def test_parse_url_no_crash(self):
        self.assertTrue(
            ProcessingRule.parse_url('http://example.com')
        )
        self.assertFalse(
            ProcessingRule.parse_url('http://')
        )
        self.assertFalse(
            ProcessingRule.parse_url('')
        )
        self.assertFalse(
            ProcessingRule.parse_url('.xn--hda.com/')
        )


def new_mock_url_record():
    url_record = URLRecord()
    url_record.url = 'http://example.com'
    url_record.parent_url = 'http://example.com'
    url_record.level = 0

    return url_record


def new_mock_item_session():
    args = argparse.Namespace(directory_prefix='/tmp/')
    app_session = AppSession(None, args, None)
    url_record = new_mock_url_record()
    item_session = ItemSession(app_session, url_record)
    item_session.request = BaseRequest()
    item_session.request.url = 'http://example.com'

    return item_session
