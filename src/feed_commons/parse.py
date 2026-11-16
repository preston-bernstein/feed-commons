from typing import Any

import feedparser
import feedparser.exceptions

from feed_commons.errors import PollErrorCode

BENIGN_BOZO_EXCEPTIONS = (
    feedparser.exceptions.CharacterEncodingOverride,
    feedparser.exceptions.NonXMLContentType,
)


def parse_feed(raw_bytes: bytes) -> Any:  # noqa: ANN401 -- feedparser ships no types
    return feedparser.parse(raw_bytes)


def classify_parse_outcome(parsed: Any) -> PollErrorCode | None:  # noqa: ANN401 -- feedparser result, no types
    if parsed.bozo != 1:
        return None

    if parsed.bozo_exception is None:
        if len(parsed.entries) == 0:
            return "parse_error"
        return None

    if isinstance(parsed.bozo_exception, BENIGN_BOZO_EXCEPTIONS):
        if len(parsed.entries) >= 1:
            return None
        return "parse_error"

    return "parse_error"
