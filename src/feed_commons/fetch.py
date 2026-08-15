from urllib.parse import urlsplit

import requests

from feed_commons.errors import PollError

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_CHUNK_SIZE = 8192
_USER_AGENT = "feed-commons/0.0.0 (+https://github.com/preston-bernstein/feed-commons)"


def validate_https_url(url: str) -> None:
    """Pure syntactic validation of a feed URL. Makes no network call.

    Raises PollError("invalid_url") if the URL is not a well-formed
    https:// URL with a non-empty host.
    """
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise PollError("invalid_url")
    if not parsed.netloc:
        raise PollError("invalid_url")


def fetch_feed_bytes(url: str, timeout_seconds: float) -> bytes:
    """Fetch the raw bytes of a feed over HTTPS.

    Validates the URL first (defense in depth), then performs a GET
    request without following redirects and without attaching any
    credentials. Enforces a 10 MB response-size cap. Raises PollError
    with a bounded, non-leaky code on any failure.
    """
    validate_https_url(url)

    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": _USER_AGENT},
        )
        try:
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError:
                    declared_length = None
                if declared_length is not None and declared_length > _MAX_RESPONSE_BYTES:
                    raise PollError("http_error")

            if not (200 <= response.status_code < 300):
                raise PollError("http_error")

            body = bytearray()
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise PollError("http_error")

            return bytes(body)
        finally:
            response.close()
    except requests.exceptions.Timeout:
        raise PollError("timeout")
    except requests.exceptions.ConnectionError:
        raise PollError("network_error")
    except requests.exceptions.RequestException:
        raise PollError("network_error")
