import types

import feedparser.exceptions

from feed_commons.parse import (
    BENIGN_BOZO_EXCEPTIONS,
    classify_parse_outcome,
    parse_feed,
)

RSS_WELL_FORMED = b"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
<title>Item 1</title>
<link>https://example.com/1</link>
</item>
</channel>
</rss>
"""

ATOM_WELL_FORMED = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Test</title>
<entry>
<title>Entry 1</title>
<id>tag:example.com,2024:1</id>
<link href="https://example.com/1"/>
</entry>
</feed>
"""

# genuinely broken XML: unclosed tags, no closing root, feedparser can't
# recover any entries from this
MALFORMED_XML_NO_ENTRIES = b"not xml at all, just garbage <<<>>> {{{"


# 1. Well-formed RSS (AC11/AC12 baseline)


def test_parse_feed_well_formed_rss_no_error():
    result = parse_feed(RSS_WELL_FORMED)
    assert classify_parse_outcome(result) is None
    assert len(result.entries) >= 1


# 2. Well-formed Atom


def test_parse_feed_well_formed_atom_no_error():
    result = parse_feed(ATOM_WELL_FORMED)
    assert classify_parse_outcome(result) is None
    assert len(result.entries) >= 1


# 3. Malformed XML with zero entries -> parse_error (AC11)


def test_parse_feed_malformed_zero_entries_is_parse_error():
    result = parse_feed(MALFORMED_XML_NO_ENTRIES)
    assert result.bozo == 1
    assert len(result.entries) == 0
    assert classify_parse_outcome(result) == "parse_error"


# 4. Benign bozo_exception with >=1 entry -> not an error (AC12)


def test_classify_benign_bozo_exception_with_entries_is_not_error():
    parsed = types.SimpleNamespace(
        bozo=1,
        bozo_exception=feedparser.exceptions.NonXMLContentType(),
        entries=[{"title": "x"}],
    )
    assert isinstance(parsed.bozo_exception, BENIGN_BOZO_EXCEPTIONS)
    assert classify_parse_outcome(parsed) is None


def test_classify_benign_bozo_exception_character_encoding_override_with_entries_is_not_error():
    parsed = types.SimpleNamespace(
        bozo=1,
        bozo_exception=feedparser.exceptions.CharacterEncodingOverride(),
        entries=[{"title": "x"}],
    )
    assert isinstance(parsed.bozo_exception, BENIGN_BOZO_EXCEPTIONS)
    assert classify_parse_outcome(parsed) is None


def test_classify_benign_bozo_exception_with_zero_entries_is_parse_error():
    parsed = types.SimpleNamespace(
        bozo=1,
        bozo_exception=feedparser.exceptions.NonXMLContentType(),
        entries=[],
    )
    assert classify_parse_outcome(parsed) == "parse_error"


# 5. bozo==1, bozo_exception is None, zero entries -> parse_error


def test_classify_bozo_no_exception_zero_entries_is_parse_error():
    parsed = types.SimpleNamespace(bozo=1, bozo_exception=None, entries=[])
    assert classify_parse_outcome(parsed) == "parse_error"


# 6. bozo==1, bozo_exception is None, >=1 entry -> not an error


def test_classify_bozo_no_exception_with_entries_is_not_error():
    parsed = types.SimpleNamespace(bozo=1, bozo_exception=None, entries=[{"title": "x"}])
    assert classify_parse_outcome(parsed) is None


# 7. Non-benign bozo_exception type -> parse_error regardless of entry count


def test_classify_non_benign_bozo_exception_is_parse_error_even_with_entries():
    parsed = types.SimpleNamespace(
        bozo=1,
        bozo_exception=ValueError("some other parse issue"),
        entries=[{"title": "x"}],
    )
    assert classify_parse_outcome(parsed) == "parse_error"


def test_classify_bozo_zero_is_never_an_error():
    parsed = types.SimpleNamespace(bozo=0, bozo_exception=None, entries=[])
    assert classify_parse_outcome(parsed) is None
