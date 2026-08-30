"""Tests for feed_commons.poll: end-to-end orchestration.

Notes on approach:

- pytest-httpserver (as installed here) only serves plain HTTP, not HTTPS,
  and fetch_feed_bytes() enforces HTTPS-only with no way to opt out. To
  exercise the real fetch -> parse -> normalize pipeline against a real
  server, validate_https_url is monkeypatched to a no-op for those tests,
  following the same idiom tests/test_fetch.py already uses. The scheme
  check itself is fully covered separately in tests/test_fetch.py, so this
  does not weaken coverage of that check.
- AC13 (no real network calls) is implicit: every test here either talks
  only to the local httpserver fixture or mocks the lower-layer functions
  directly, matching the rest of this repo's test suite.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from feed_commons.errors import PollError
from feed_commons.poll import _PollOutcome, _run_poll, poll


def _bypass_scheme_check():
    """No-op the HTTPS-only check inside fetch.py for tests that need to hit
    a real (plain-HTTP) local test server. See module docstring above.
    """
    return patch("feed_commons.fetch.validate_https_url", lambda url: None)


RSS_TWO_VALID_ITEMS = b"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
<title>Item 1</title>
<link>https://example.com/1</link>
<description>First item body</description>
</item>
<item>
<title>Item 2</title>
<link>https://example.com/2</link>
<description>Second item body</description>
</item>
</channel>
</rss>
"""

RSS_MIXED_VALID_INVALID = b"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Mixed Feed</title>
<item>
<title>Valid Item 1</title>
<link>https://example.com/valid1</link>
</item>
<item>
<title></title>
<link>https://example.com/no-title</link>
</item>
<item>
<title>No Link Item</title>
<link></link>
</item>
<item>
<title>Valid Item 2</title>
<link>https://example.com/valid2</link>
</item>
</channel>
</rss>
"""


# --- AC6: successful fetch + parse -> normalized items, no error ----------


def test_poll_returns_normalized_items_on_success(httpserver):
    httpserver.expect_request("/feed.xml").respond_with_data(
        RSS_TWO_VALID_ITEMS, content_type="application/rss+xml"
    )
    url = httpserver.url_for("/feed.xml")

    with _bypass_scheme_check():
        items = poll(url, excerpt_max_length=300, timeout_seconds=5)

    assert isinstance(items, list)
    assert len(items) == 2

    titles = {item["title"] for item in items}
    links = {item["link"] for item in items}
    assert titles == {"Item 1", "Item 2"}
    assert links == {"https://example.com/1", "https://example.com/2"}
    for item in items:
        assert item["title"]
        assert item["link"]
        assert item["guid"]


# --- skipped_count wiring (via _run_poll directly) -------------------------


def test_run_poll_reports_items_and_skipped_count(httpserver):
    httpserver.expect_request("/mixed.xml").respond_with_data(
        RSS_MIXED_VALID_INVALID, content_type="application/rss+xml"
    )
    url = httpserver.url_for("/mixed.xml")

    with _bypass_scheme_check():
        outcome = _run_poll(url, 300, 15)

    assert isinstance(outcome, _PollOutcome)
    assert len(outcome.items) == 2
    titles = {item["title"] for item in outcome.items}
    assert titles == {"Valid Item 1", "Valid Item 2"}
    assert outcome.skipped_count == 2


# --- AC19 (first half): unanticipated exception -> network_error ----------


def test_run_poll_maps_unanticipated_exception_to_network_error():
    with patch(
        "feed_commons.poll.fetch_feed_bytes",
        side_effect=ValueError("boom, unexpected"),
    ), pytest.raises(PollError) as exc_info:
        _run_poll("https://example.com/feed.xml", 300, 15)

    assert exc_info.value.code == "network_error"
    assert "boom, unexpected" not in str(exc_info.value)
    assert "boom, unexpected" not in exc_info.value.code


# --- AC19 (second half): a PollError from a lower layer propagates --------
# unchanged, NOT reclassified to network_error. This is the key regression
# guard for the `except PollError: raise` ordering in _run_poll.


def test_run_poll_propagates_lower_layer_poll_error_unchanged():
    with patch(
        "feed_commons.poll.fetch_feed_bytes",
        side_effect=PollError("timeout"),
    ), pytest.raises(PollError) as exc_info:
        _run_poll("https://example.com/feed.xml", 300, 15)

    assert exc_info.value.code == "timeout"
    assert exc_info.value.code != "network_error"


def test_run_poll_logs_unanticipated_exception_message_and_logger(caplog):
    """Pins the exact logger name, message text, and %r-formatted argument
    used by the debug log call in the `except Exception` branch. Mutations
    to any piece of this call (message text, logger name, missing/None
    argument, dropped % formatting) must change either the emitted message
    string or the logger's name.
    """
    exc = ValueError("boom, unexpected")
    with (
        caplog.at_level(logging.DEBUG, logger="feed_commons.poll"),
        patch("feed_commons.poll.fetch_feed_bytes", side_effect=exc),
        pytest.raises(PollError),
    ):
        _run_poll("https://example.com/feed.xml", 300, 15)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == "feed_commons.poll"
    assert record.getMessage() == f"unanticipated exception in _run_poll: {exc!r}"


# --- argument-passing wiring inside _run_poll ------------------------------


def test_run_poll_calls_fetch_feed_bytes_with_url_and_timeout_seconds():
    with (
        patch("feed_commons.poll.fetch_feed_bytes", return_value=b"data") as mock_fetch,
        patch("feed_commons.poll.parse_feed", return_value=SimpleNamespace(entries=[])),
        patch("feed_commons.poll.classify_parse_outcome", return_value=None),
    ):
        _run_poll("https://example.com/feed.xml", 300, 42)

    mock_fetch.assert_called_once_with("https://example.com/feed.xml", 42)


def test_run_poll_raises_poll_error_with_exact_classify_parse_outcome_code():
    """Pins that the PollError raised for a classified parse failure carries
    the *actual* error_code returned by classify_parse_outcome, not a stub
    or None. If classify_parse_outcome's return value were ignored (or the
    error_code were dropped when constructing PollError), this would either
    fail to raise at all or raise with the wrong code.
    """
    with (
        patch("feed_commons.poll.fetch_feed_bytes", return_value=b"data"),
        patch("feed_commons.poll.parse_feed", return_value=object()),
        patch("feed_commons.poll.classify_parse_outcome", return_value="malformed_feed") as mock_classify,
        pytest.raises(PollError) as exc_info,
    ):
        _run_poll("https://example.com/feed.xml", 300, 15)

    mock_classify.assert_called_once()
    assert exc_info.value.code == "malformed_feed"


def test_run_poll_calls_normalize_entry_with_excerpt_max_length():
    entry = object()
    with (
        patch("feed_commons.poll.fetch_feed_bytes", return_value=b"data"),
        patch("feed_commons.poll.parse_feed", return_value=SimpleNamespace(entries=[entry])),
        patch("feed_commons.poll.classify_parse_outcome", return_value=None),
        patch("feed_commons.poll.normalize_entry", return_value=None) as mock_normalize,
    ):
        _run_poll("https://example.com/feed.xml", 123, 15)

    mock_normalize.assert_called_once_with(entry, 123)


# --- poll() wiring to _run_poll, including its defaults --------------------


def test_poll_calls_run_poll_with_defaults_and_returns_its_items():
    outcome = _PollOutcome(items=[], skipped_count=0)
    with patch("feed_commons.poll._run_poll", return_value=outcome) as mock_run_poll:
        result = poll("https://example.com/feed.xml")

    mock_run_poll.assert_called_once_with("https://example.com/feed.xml", 300, 15)
    assert result == outcome.items
