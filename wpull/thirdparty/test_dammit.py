# -*- coding: utf-8 -*-
"""Tests of Beautiful Soup as a whole."""
# Copyright (c) 2004-2012 Leonard Richardson
# Beautiful Soup is made available under the MIT license

import unittest
import wpull.thirdparty.dammit
from wpull.thirdparty.dammit import (
    EntitySubstitution,
    UnicodeDammit,
)


class TestEntitySubstitution(unittest.TestCase):
    """Standalone tests of the EntitySubstitution class."""
    def setUp(self):
        self.sub = EntitySubstitution

    def test_simple_html_substitution(self):
        # Unicode characters corresponding to named HTML entites
        # are substituted, and no others.
        s = "foo\u2200\N{SNOWMAN}\u00f5bar"
        self.assertEqual(self.sub.substitute_html(s),
                         "foo&forall;\N{SNOWMAN}&otilde;bar")

    def test_smart_quote_substitution(self):
        # MS smart quotes are a common source of frustration, so we
        # give them a special test.
        quotes = b"\x91\x92foo\x93\x94"
        dammit = UnicodeDammit(quotes)
        self.assertEqual(self.sub.substitute_html(dammit.markup),
                         "&lsquo;&rsquo;foo&ldquo;&rdquo;")

    def test_xml_converstion_includes_no_quotes_if_make_quoted_attribute_is_false(self):
        s = 'Welcome to "my bar"'
        self.assertEqual(self.sub.substitute_xml(s, False), s)

    def test_xml_attribute_quoting_normally_uses_double_quotes(self):
        self.assertEqual(self.sub.substitute_xml("Welcome", True),
                         '"Welcome"')
        self.assertEqual(self.sub.substitute_xml("Bob's Bar", True),
                         '"Bob\'s Bar"')

    def test_xml_attribute_quoting_uses_single_quotes_when_value_contains_double_quotes(self):
        s = 'Welcome to "my bar"'
        self.assertEqual(self.sub.substitute_xml(s, True),
                          "'Welcome to \"my bar\"'")

    def test_xml_attribute_quoting_escapes_single_quotes_when_value_contains_both_single_and_double_quotes(self):
        s = 'Welcome to "Bob\'s Bar"'
        self.assertEqual(
            self.sub.substitute_xml(s, True),
            '"Welcome to &quot;Bob\'s Bar&quot;"')

    def test_xml_quotes_arent_escaped_when_value_is_not_being_quoted(self):
        quoted = 'Welcome to "Bob\'s Bar"'
        self.assertEqual(self.sub.substitute_xml(quoted), quoted)

    def test_xml_quoting_handles_angle_brackets(self):
        self.assertEqual(
            self.sub.substitute_xml("foo<bar>"),
            "foo&lt;bar&gt;")

    def test_xml_quoting_handles_ampersands(self):
        self.assertEqual(self.sub.substitute_xml("AT&T"), "AT&amp;T")

    def test_xml_quoting_including_ampersands_when_they_are_part_of_an_entity(self):
        self.assertEqual(
            self.sub.substitute_xml("&Aacute;T&T"),
            "&amp;Aacute;T&amp;T")

    def test_xml_quoting_ignoring_ampersands_when_they_are_part_of_an_entity(self):
        self.assertEqual(
            self.sub.substitute_xml_containing_entities("&Aacute;T&T"),
            "&Aacute;T&amp;T")

    def test_quotes_not_html_substituted(self):
        """There's no need to do this except inside attribute values."""
        text = 'Bob\'s "bar"'
        self.assertEqual(self.sub.substitute_html(text), text)


class TestUnicodeDammit(unittest.TestCase):
    """Standalone tests of UnicodeDammit."""

    def test_unicode_input(self):
        markup = "I'm already Unicode! \N{SNOWMAN}"
        dammit = UnicodeDammit(markup)
        self.assertEqual(dammit.unicode_markup, markup)

    def test_smart_quotes_to_unicode(self):
        markup = b"<foo>\x91\x92\x93\x94</foo>"
        dammit = UnicodeDammit(markup)
        self.assertEqual(
            dammit.unicode_markup, "<foo>\u2018\u2019\u201c\u201d</foo>")

    def test_smart_quotes_to_xml_entities(self):
        markup = b"<foo>\x91\x92\x93\x94</foo>"
        dammit = UnicodeDammit(markup, smart_quotes_to="xml")
        self.assertEqual(
            dammit.unicode_markup, "<foo>&#x2018;&#x2019;&#x201C;&#x201D;</foo>")

    def test_smart_quotes_to_html_entities(self):
        markup = b"<foo>\x91\x92\x93\x94</foo>"
        dammit = UnicodeDammit(markup, smart_quotes_to="html")
        self.assertEqual(
            dammit.unicode_markup, "<foo>&lsquo;&rsquo;&ldquo;&rdquo;</foo>")

    def test_smart_quotes_to_ascii(self):
        markup = b"<foo>\x91\x92\x93\x94</foo>"
        dammit = UnicodeDammit(markup, smart_quotes_to="ascii")
        self.assertEqual(
            dammit.unicode_markup, """<foo>''""</foo>""")

    def test_detect_utf8(self):
        utf8 = b"\xc3\xa9\xc3\xa9"
        dammit = UnicodeDammit(utf8)
        self.assertEqual(dammit.unicode_markup, '\xe9\xe9')
        self.assertEqual(dammit.original_encoding.lower(), 'utf-8')

    def test_convert_hebrew(self):
        hebrew = b"\xed\xe5\xec\xf9"
        dammit = UnicodeDammit(hebrew, ["iso-8859-8"])
        self.assertEqual(dammit.original_encoding.lower(), 'iso-8859-8')
        self.assertEqual(dammit.unicode_markup, '\u05dd\u05d5\u05dc\u05e9')

    def test_dont_see_smart_quotes_where_there_are_none(self):
        utf_8 = b"\343\202\261\343\203\274\343\202\277\343\202\244 Watch"
        dammit = UnicodeDammit(utf_8)
        self.assertEqual(dammit.original_encoding.lower(), 'utf-8')
        self.assertEqual(dammit.unicode_markup.encode("utf-8"), utf_8)

    def test_ignore_inappropriate_codecs(self):
        utf8_data = "Räksmörgås".encode("utf-8")
        dammit = UnicodeDammit(utf8_data, ["iso-8859-8"])
        self.assertEqual(dammit.original_encoding.lower(), 'utf-8')

    def test_ignore_invalid_codecs(self):
        utf8_data = "Räksmörgås".encode("utf-8")
        for bad_encoding in ['.utf8', '...', 'utF---16.!']:
            dammit = UnicodeDammit(utf8_data, [bad_encoding])
            self.assertEqual(dammit.original_encoding.lower(), 'utf-8')

    def test_detect_html5_style_meta_tag(self):

        for data in (
            b'<html><meta charset="euc-jp" /></html>',
            b"<html><meta charset='euc-jp' /></html>",
            b"<html><meta charset=euc-jp /></html>",
            b"<html><meta charset=euc-jp/></html>"):
            dammit = UnicodeDammit(data, is_html=True)
            self.assertEqual(
                "euc-jp", dammit.original_encoding)

    def test_byte_order_mark_removed(self):
        # A document written in UTF-16LE will have its byte order marker stripped.
        data = b'\xff\xfe<\x00a\x00>\x00\xe1\x00\xe9\x00<\x00/\x00a\x00>\x00'
        dammit = UnicodeDammit(data)
        self.assertEqual("<a>áé</a>", dammit.unicode_markup)
        self.assertEqual("utf-16le", dammit.original_encoding)

    def test_detwingle(self):
        # Here's a UTF8 document.
        utf8 = ("\N{SNOWMAN}" * 3).encode("utf8")

        # Here's a Windows-1252 document.
        windows_1252 = (
            "\N{LEFT DOUBLE QUOTATION MARK}Hi, I like Windows!"
            "\N{RIGHT DOUBLE QUOTATION MARK}").encode("windows_1252")

        # Through some unholy alchemy, they've been stuck together.
        doc = utf8 + windows_1252 + utf8

        # The document can't be turned into UTF-8:
        self.assertRaises(UnicodeDecodeError, doc.decode, "utf8")

        # Unicode, Dammit thinks the whole document is Windows-1252,
        # and decodes it into "â˜ƒâ˜ƒâ˜ƒ“Hi, I like Windows!”â˜ƒâ˜ƒâ˜ƒ"

        # But if we run it through fix_embedded_windows_1252, it's fixed:

        fixed = UnicodeDammit.detwingle(doc)
        self.assertEqual(
            "☃☃☃“Hi, I like Windows!”☃☃☃", fixed.decode("utf8"))

    def test_detwingle_ignores_multibyte_characters(self):
        # Each of these characters has a UTF-8 representation ending
        # in \x93. \x93 is a smart quote if interpreted as
        # Windows-1252. But our code knows to skip over multibyte
        # UTF-8 characters, so they'll survive the process unscathed.
        for tricky_unicode_char in (
            "\N{LATIN SMALL LIGATURE OE}",  # 2-byte char '\xc5\x93'
            "\N{LATIN SUBSCRIPT SMALL LETTER X}",  # 3-byte char '\xe2\x82\x93'
            "\xf0\x90\x90\x93",  # This is a CJK character, not sure which one.
            ):
            input = tricky_unicode_char.encode("utf8")
            self.assertTrue(input.endswith(b'\x93'))
            output = UnicodeDammit.detwingle(input)
            self.assertEqual(output, input)
