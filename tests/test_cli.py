"""Tests for feed_commons.cli: CLI output and exit-code behavior.

Notes on approach:

- pytest-httpserver (as installed here) only serves plain HTTP, not HTTPS,
  and fetch_feed_bytes() enforces HTTPS-only with no way to opt out. For the
  in-process tests (which call main() directly, in this same process),
  validate_https_url is monkeypatched to a no-op so the real fetch -> parse
  -> normalize -> CLI-envelope pipeline can be exercised against a real
  local server, following the same idiom already used in tests/test_fetch.py
  and tests/test_poll.py.
- The subprocess-level test spawns a genuinely separate Python process via
  `python -m feed_commons ...`, so no monkeypatch from this process applies
  there. A plain-http httpserver URL is therefore correctly rejected by the
  real, unpatched validate_https_url as "invalid_url". That's still a
  meaningful end-to-end check: it proves the __main__.py / `python -m`
  wiring, argument parsing, stdout JSON emission, and exit code all work in
  a real separate process, even though it can't exercise the full
  successful-fetch path without a real HTTPS server.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from feed_commons.cli import _build_parser, main
from feed_commons.errors import PollError
from feed_commons.poll import _PollOutcome

REPO_ROOT = Path(__file__).resolve().parent.parent


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


# --- AC14: all-clean feed -> status ok, exit code 0 ------------------------


def test_main_prints_ok_status_and_returns_zero_on_clean_feed(httpserver, capsys):
    httpserver.expect_request("/feed.xml").respond_with_data(
        RSS_TWO_VALID_ITEMS, content_type="application/rss+xml"
    )
    url = httpserver.url_for("/feed.xml")

    with _bypass_scheme_check():
        exit_code = main(["poll", url, "--json"])

    assert exit_code == 0

    captured = capsys.readouterr()
    output_line = captured.out.strip()
    envelope = json.loads(output_line)

    assert envelope["status"] == "ok"
    assert envelope["error"] is None
    assert isinstance(envelope["items"], list)
    assert len(envelope["items"]) == 2


# --- AC15: mixed feed with skipped entries -> status degraded --------------


def test_main_prints_degraded_status_when_entries_are_skipped(httpserver, capsys):
    httpserver.expect_request("/mixed.xml").respond_with_data(
        RSS_MIXED_VALID_INVALID, content_type="application/rss+xml"
    )
    url = httpserver.url_for("/mixed.xml")

    with _bypass_scheme_check():
        exit_code = main(["poll", url, "--json"])

    assert exit_code == 0

    captured = capsys.readouterr()
    envelope = json.loads(captured.out.strip())

    assert envelope["status"] == "degraded"
    assert envelope["error"] is None
    assert len(envelope["items"]) == 2
    titles = {item["title"] for item in envelope["items"]}
    assert titles == {"Valid Item 1", "Valid Item 2"}


# --- AC16: HTTP 500 -> status fail, exit code 1 -----------------------------


def test_main_prints_fail_status_and_returns_nonzero_on_http_error(
    httpserver, capsys
):
    httpserver.expect_request("/broken.xml").respond_with_data(
        "server error", status=500
    )
    url = httpserver.url_for("/broken.xml")

    with _bypass_scheme_check():
        exit_code = main(["poll", url, "--json"])

    assert exit_code == 1

    captured = capsys.readouterr()
    envelope = json.loads(captured.out.strip())

    assert envelope["status"] == "fail"
    assert envelope["items"] == []
    assert envelope["error"] == "http_error"
    assert envelope["error"] in {
        "timeout",
        "invalid_url",
        "http_error",
        "parse_error",
        "network_error",
    }


# --- Subprocess-level end-to-end: real `python -m feed_commons` process ----


def test_subprocess_cli_rejects_non_https_url_with_real_process(httpserver):
    url = httpserver.url_for("/feed.xml")
    assert url.startswith("http://")

    result = subprocess.run(
        [sys.executable, "-m", "feed_commons", "poll", url, "--json"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )

    assert result.returncode == 1

    envelope = json.loads(result.stdout.strip())
    assert envelope["status"] == "fail"
    assert envelope["items"] == []
    assert envelope["error"] == "invalid_url"


def test_subprocess_cli_help_exits_zero_without_traceback():
    result = subprocess.run(
        [sys.executable, "-m", "feed_commons", "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


# --- _build_parser: exact structure, dest, required-ness, help text --------


def test_build_parser_prog_is_feed_commons():
    parser = _build_parser()
    assert parser.prog == "feed_commons"


def test_build_parser_dest_is_command_and_parses_poll():
    parser = _build_parser()
    args = parser.parse_args(["poll", "https://example.com/feed.xml"])
    # dest must be exactly "command" for this attribute to exist at all.
    assert args.command == "poll"
    assert args.url == "https://example.com/feed.xml"
    assert args.json is False


def test_build_parser_missing_subcommand_is_required_and_exits_nonzero():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])
    assert exc_info.value.code != 0


def test_build_parser_poll_missing_url_exits_nonzero():
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["poll"])
    assert exc_info.value.code != 0


def test_build_parser_top_level_help_lists_poll_with_exact_help_text(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    # Exact full-text match (not a substring check): a mutmut string mutation
    # like help="XXpoll a feed URL...JSONXX" still contains the original text
    # as a substring, so only an exact match on the whole rendered help
    # output catches it.
    assert out == (
        "usage: feed_commons [-h] {poll} ...\n"
        "\n"
        "positional arguments:\n"
        "  {poll}\n"
        "    poll      poll a feed URL and print normalized items as JSON\n"
        "\n"
        "options:\n"
        "  -h, --help  show this help message and exit\n"
    )


def test_build_parser_poll_subparser_help_lists_url_and_json_exact_text(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["poll", "--help"])
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    # Exact full-text match for the same reason as the top-level help test
    # above: substring checks don't catch mutmut's XX-wrapped string mutants.
    assert out == (
        "usage: feed_commons poll [-h] [--json] url\n"
        "\n"
        "positional arguments:\n"
        "  url         the feed URL to poll\n"
        "\n"
        "options:\n"
        "  -h, --help  show this help message and exit\n"
        "  --json      output as JSON (always on)\n"
    )


# --- main(): exact argument pass-through to _run_poll ----------------------


def test_main_calls_run_poll_with_exact_pinned_arguments():
    fake_outcome = _PollOutcome(items=[], skipped_count=0)
    with patch("feed_commons.cli._run_poll", return_value=fake_outcome) as mock_run_poll:
        main(["poll", "https://example.com/feed.xml", "--json"])

    mock_run_poll.assert_called_once_with("https://example.com/feed.xml", 300, 15)


# --- main(): exact JSON envelope + exit code per outcome --------------------


def test_main_ok_outcome_prints_exact_envelope_and_returns_zero(capsys):
    fake_outcome = _PollOutcome(items=[{"title": "Item 1"}], skipped_count=0)
    with patch("feed_commons.cli._run_poll", return_value=fake_outcome):
        exit_code = main(["poll", "https://example.com/feed.xml", "--json"])

    assert exit_code == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert set(envelope.keys()) == {"status", "items", "error"}
    assert envelope == {
        "status": "ok",
        "items": [{"title": "Item 1"}],
        "error": None,
    }


def test_main_degraded_outcome_boundary_at_exactly_one_skipped(capsys):
    # skipped_count > 0 is the real boundary: exactly 1 must already be degraded.
    fake_outcome = _PollOutcome(items=[{"title": "Item 1"}], skipped_count=1)
    with patch("feed_commons.cli._run_poll", return_value=fake_outcome):
        exit_code = main(["poll", "https://example.com/feed.xml", "--json"])

    assert exit_code == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert set(envelope.keys()) == {"status", "items", "error"}
    assert envelope == {
        "status": "degraded",
        "items": [{"title": "Item 1"}],
        "error": None,
    }


def test_main_zero_skipped_is_not_degraded(capsys):
    fake_outcome = _PollOutcome(items=[{"title": "Item 1"}], skipped_count=0)
    with patch("feed_commons.cli._run_poll", return_value=fake_outcome):
        exit_code = main(["poll", "https://example.com/feed.xml", "--json"])

    assert exit_code == 0

    envelope = json.loads(capsys.readouterr().out.strip())
    assert envelope["status"] == "ok"


def test_main_fail_outcome_prints_exact_envelope_and_returns_one(capsys):
    with patch("feed_commons.cli._run_poll", side_effect=PollError("http_error")):
        exit_code = main(["poll", "https://example.com/feed.xml", "--json"])

    assert exit_code == 1

    envelope = json.loads(capsys.readouterr().out.strip())
    assert set(envelope.keys()) == {"status", "items", "error"}
    assert envelope == {
        "status": "fail",
        "items": [],
        "error": "http_error",
    }
