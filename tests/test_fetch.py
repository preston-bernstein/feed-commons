"""Tests for feed_commons.fetch: URL validation and byte-fetching behavior.

Notes on approach:

- validate_https_url() is pure (no network) and is tested directly with
  plain strings for the invalid-scheme / missing-netloc cases (AC1, AC2).
- fetch_feed_bytes() calls validate_https_url() first, so a plain http://
  URL is rejected before any request is attempted (AC1, verified against
  no matcher being configured on the test server and an empty request log).
- pytest-httpserver (as installed here) only serves plain HTTP, not HTTPS,
  and fetch_feed_bytes() enforces HTTPS-only with no way to opt out. To
  exercise the real requests.get()-based fetch/timeout/error-classification
  logic (AC3, AC4, AC5, AC21, credential/header behavior) against a real
  server, validate_https_url is monkeypatched to a no-op for just those
  tests. The scheme/netloc checks themselves are already fully covered
  separately above, so this does not weaken coverage of those checks.
"""

from __future__ import annotations

import socket
import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from werkzeug.wrappers import Request, Response

from feed_commons.errors import PollError
from feed_commons.fetch import (
    _CHUNK_SIZE,
    _USER_AGENT,
    fetch_feed_bytes,
    validate_https_url,
)


def _bypass_scheme_check():
    """Context manager that no-ops the HTTPS-only check inside fetch.py.

    Used only for tests that need to exercise the real network/HTTP
    handling logic of fetch_feed_bytes() against a plain-HTTP test server.
    The scheme check itself is covered directly and separately below.
    """
    return patch("feed_commons.fetch.validate_https_url", lambda url: None)


# --- AC1: invalid scheme -----------------------------------------------


def test_validate_https_url_rejects_http_scheme():
    with pytest.raises(PollError) as exc_info:
        validate_https_url("http://example.com/feed.xml")
    assert exc_info.value.code == "invalid_url"


def test_fetch_feed_bytes_rejects_http_scheme_without_network_call(httpserver):
    # Deliberately no expect_request() configured: if a real request were
    # made, pytest-httpserver would either raise or log it. We assert
    # neither happens.
    url = httpserver.url_for("/feed.xml")  # http://localhost:PORT/feed.xml
    assert url.startswith("http://")

    with pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 5)
    assert exc_info.value.code == "invalid_url"

    assert len(httpserver.log) == 0


# --- AC2: malformed URL (no netloc) -------------------------------------


def test_validate_https_url_rejects_missing_netloc():
    with pytest.raises(PollError) as exc_info:
        validate_https_url("https://")
    assert exc_info.value.code == "invalid_url"


def test_validate_https_url_rejects_missing_netloc_with_path():
    with pytest.raises(PollError) as exc_info:
        validate_https_url("https:///path")
    assert exc_info.value.code == "invalid_url"


def test_validate_https_url_accepts_well_formed_https_url():
    # No exception should be raised for a well-formed https:// URL with a
    # non-empty host. This pins down the real (non-inverted, non-corrupted)
    # scheme comparison and the real `url` argument being parsed.
    validate_https_url("https://example.com/feed.xml")


# --- AC3: timeout ---------------------------------------------------------


def test_fetch_feed_bytes_raises_timeout(httpserver):
    def slow_handler(request: Request) -> Response:
        time.sleep(2)
        return Response("too slow", status=200)

    httpserver.expect_request("/slow").respond_with_handler(slow_handler)
    url = httpserver.url_for("/slow")

    with _bypass_scheme_check(), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 0.2)
    assert exc_info.value.code == "timeout"


# --- AC4: non-2xx status -> http_error ------------------------------------


def test_fetch_feed_bytes_raises_http_error_on_404(httpserver):
    httpserver.expect_request("/missing.xml").respond_with_data(
        "not found", status=404
    )
    url = httpserver.url_for("/missing.xml")

    with _bypass_scheme_check(), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 5)
    assert exc_info.value.code == "http_error"


def test_fetch_feed_bytes_raises_http_error_on_500(httpserver):
    httpserver.expect_request("/broken.xml").respond_with_data(
        "server error", status=500
    )
    url = httpserver.url_for("/broken.xml")

    with _bypass_scheme_check(), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 5)
    assert exc_info.value.code == "http_error"


# --- AC5: connection refused -> network_error -----------------------------


def test_fetch_feed_bytes_raises_network_error_on_connection_refused():
    # Bind to an ephemeral port, grab it, then close the socket so nothing
    # is listening there anymore.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()

    url = f"http://127.0.0.1:{port}/feed.xml"

    with _bypass_scheme_check(), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 5)
    assert exc_info.value.code == "network_error"


# --- AC21: redirect to http:// is never followed --------------------------


def test_fetch_feed_bytes_does_not_follow_redirect(httpserver):
    httpserver.expect_request("/redirect").respond_with_data(
        "", status=302, headers={"Location": "http://evil.example.com/"}
    )
    url = httpserver.url_for("/redirect")

    with _bypass_scheme_check(), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes(url, 5)
    assert exc_info.value.code == "http_error"

    # Only the /redirect request itself was made; the redirect target was
    # never followed (allow_redirects=False in fetch.py). Confirm the
    # request log contains exactly the one request to /redirect.
    assert len(httpserver.log) == 1
    logged_request, _ = httpserver.log[0]
    assert logged_request.path == "/redirect"


# --- No credential/auth headers; custom User-Agent is sent ---------------


def test_fetch_feed_bytes_sends_no_credentials_and_custom_user_agent(httpserver):
    captured_headers = {}

    def capturing_handler(request: Request) -> Response:
        captured_headers.update(request.headers)
        return Response("ok", status=200)

    httpserver.expect_request("/feed.xml").respond_with_handler(capturing_handler)
    url = httpserver.url_for("/feed.xml")

    with _bypass_scheme_check():
        body = fetch_feed_bytes(url, 5)

    assert body == b"ok"
    assert "Authorization" not in captured_headers
    assert "Cookie" not in captured_headers
    assert captured_headers.get("User-Agent") == _USER_AGENT
    assert captured_headers.get("User-Agent") != "python-requests"


# --- Mock-based tests: real validate_https_url + mocked requests.get ------
#
# The httpserver-based tests above all monkeypatch validate_https_url to a
# no-op (necessary since pytest-httpserver only serves plain HTTP). That
# no-op discards its argument entirely, so it can never observe a mutation
# that corrupts the value/order of the validate_https_url(url) call inside
# fetch_feed_bytes. These tests instead mock requests.get directly and pass
# a real, syntactically valid "https://..." URL, so the REAL
# validate_https_url runs against a real argument.


def _make_mock_response(status_code=200, headers=None, chunks=(b"ok",)):
    response = MagicMock()
    response.status_code = status_code
    # A plain dict (not a case-insensitive multidict, unlike a real
    # requests.Response.headers) is deliberate: fetch.py must look up
    # "Content-Length" with that exact casing, so a plain dict makes a
    # wrong-case lookup in fetch.py observably fail to find the header.
    response.headers = dict(headers) if headers is not None else {}
    response.iter_content.return_value = list(chunks)
    return response


def test_fetch_feed_bytes_validates_real_url_and_calls_requests_get_correctly():
    mock_response = _make_mock_response(status_code=200, chunks=[b"<rss></rss>"])
    with patch(
        "feed_commons.fetch.requests.get", return_value=mock_response
    ) as mock_get:
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)

    assert result == b"<rss></rss>"
    mock_get.assert_called_once()
    call_args, call_kwargs = mock_get.call_args
    assert call_args[0] == "https://example.com/feed.xml"  # the real, uncorrupted url
    assert call_kwargs["timeout"] == 15
    assert call_kwargs["allow_redirects"] is False
    assert call_kwargs["stream"] is True
    assert call_kwargs["headers"] == {"User-Agent": _USER_AGENT}
    mock_response.iter_content.assert_called_once_with(chunk_size=_CHUNK_SIZE)


def test_fetch_feed_bytes_rejects_non_https_url_before_calling_requests_get():
    mock_response = _make_mock_response()
    with patch(
        "feed_commons.fetch.requests.get", return_value=mock_response
    ) as mock_get, pytest.raises(PollError) as exc_info:
        fetch_feed_bytes("http://not-https.com/feed.xml", 15)

    assert exc_info.value.code == "invalid_url"
    mock_get.assert_not_called()


def test_fetch_feed_bytes_raises_http_error_on_mocked_non_2xx_status():
    mock_response = _make_mock_response(status_code=500)
    with (
        patch("feed_commons.fetch.requests.get", return_value=mock_response),
        pytest.raises(PollError) as exc_info,
    ):
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "http_error"


def test_fetch_feed_bytes_accepts_status_299_as_success():
    mock_response = _make_mock_response(status_code=299, chunks=[b"ok"])
    with patch("feed_commons.fetch.requests.get", return_value=mock_response):
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert result == b"ok"


def test_fetch_feed_bytes_rejects_status_300_as_http_error():
    # 300 is the exclusive upper bound: 200 <= status < 300. This pins the
    # boundary against both a "<=" and a "<301" corruption of the check.
    mock_response = _make_mock_response(status_code=300, chunks=[b"ok"])
    with (
        patch("feed_commons.fetch.requests.get", return_value=mock_response),
        pytest.raises(PollError) as exc_info,
    ):
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "http_error"


def test_fetch_feed_bytes_content_length_header_over_cap_raises_without_reading_body(
    monkeypatch,
):
    monkeypatch.setattr("feed_commons.fetch._MAX_RESPONSE_BYTES", 10)
    mock_response = _make_mock_response(
        status_code=200, headers={"Content-Length": "1000"}, chunks=[b"unused"]
    )
    with (
        patch("feed_commons.fetch.requests.get", return_value=mock_response),
        pytest.raises(PollError) as exc_info,
    ):
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "http_error"
    # The declared Content-Length alone is enough to reject the response;
    # the body must never be read.
    mock_response.iter_content.assert_not_called()


def test_fetch_feed_bytes_content_length_header_exactly_at_cap_succeeds(monkeypatch):
    monkeypatch.setattr("feed_commons.fetch._MAX_RESPONSE_BYTES", 10)
    mock_response = _make_mock_response(
        status_code=200,
        headers={"Content-Length": "10"},
        chunks=[b"0123456789"],  # exactly 10 bytes
    )
    with patch("feed_commons.fetch.requests.get", return_value=mock_response):
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert result == b"0123456789"


def test_fetch_feed_bytes_content_length_header_non_integer_is_ignored():
    # A malformed Content-Length must not block the fetch or crash; it is
    # simply treated as absent, and the real body size still governs.
    mock_response = _make_mock_response(
        status_code=200, headers={"Content-Length": "not-a-number"}, chunks=[b"ok"]
    )
    with patch("feed_commons.fetch.requests.get", return_value=mock_response):
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert result == b"ok"


def test_fetch_feed_bytes_body_size_exactly_at_cap_succeeds(monkeypatch):
    monkeypatch.setattr("feed_commons.fetch._MAX_RESPONSE_BYTES", 10)
    mock_response = _make_mock_response(
        status_code=200, headers={}, chunks=[b"0123456789"]  # exactly 10 bytes
    )
    with patch("feed_commons.fetch.requests.get", return_value=mock_response):
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert result == b"0123456789"


def test_fetch_feed_bytes_body_size_over_cap_raises_http_error(monkeypatch):
    monkeypatch.setattr("feed_commons.fetch._MAX_RESPONSE_BYTES", 10)
    mock_response = _make_mock_response(
        status_code=200, headers={}, chunks=[b"12345", b"67890", b"X"]  # 11 bytes total
    )
    with (
        patch("feed_commons.fetch.requests.get", return_value=mock_response),
        pytest.raises(PollError) as exc_info,
    ):
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "http_error"


def test_fetch_feed_bytes_skips_empty_chunks_without_stopping_the_stream():
    # An empty chunk mid-stream must be skipped (continue), not treated as
    # end-of-stream (break) -- later chunks must still be collected.
    mock_response = _make_mock_response(status_code=200, headers={}, chunks=[b"", b"data"])
    with patch("feed_commons.fetch.requests.get", return_value=mock_response):
        result = fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert result == b"data"


# --- Mock-based tests: requests exceptions map to the right PollError code -


def test_fetch_feed_bytes_maps_connect_timeout_to_timeout_code():
    with patch(
        "feed_commons.fetch.requests.get",
        side_effect=requests.exceptions.ConnectTimeout(),
    ), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "timeout"


def test_fetch_feed_bytes_maps_read_timeout_to_timeout_code():
    with patch(
        "feed_commons.fetch.requests.get",
        side_effect=requests.exceptions.ReadTimeout(),
    ), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "timeout"


def test_fetch_feed_bytes_maps_connection_error_to_network_error_code():
    with patch(
        "feed_commons.fetch.requests.get",
        side_effect=requests.exceptions.ConnectionError(),
    ), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "network_error"


def test_fetch_feed_bytes_maps_generic_request_exception_to_network_error_code():
    # A RequestException that is neither a Timeout nor a ConnectionError
    # (e.g. requests.exceptions.TooManyRedirects, or any other subclass)
    # must still fall through to the final, catch-all except clause and
    # map to "network_error" -- this directly exercises that last except
    # block's own raise statement, distinct from the ones above it.
    class SomeOtherRequestException(requests.exceptions.RequestException):
        pass

    with patch(
        "feed_commons.fetch.requests.get",
        side_effect=SomeOtherRequestException(),
    ), pytest.raises(PollError) as exc_info:
        fetch_feed_bytes("https://example.com/feed.xml", 15)
    assert exc_info.value.code == "network_error"
