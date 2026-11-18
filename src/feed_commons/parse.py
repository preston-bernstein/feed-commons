from typing import Any, Protocol, cast

import feedparser
import feedparser.exceptions

from feed_commons.errors import PollErrorCode

BENIGN_BOZO_EXCEPTIONS = (
    feedparser.exceptions.CharacterEncodingOverride,
    feedparser.exceptions.NonXMLContentType,
)


class ParsedFeed(Protocol):
    """The part of a feedparser result this package reads. feedparser ships no types."""

    bozo: int
    bozo_exception: object
    entries: list[dict[str, Any]]


def parse_feed(raw_bytes: bytes) -> ParsedFeed:
    return cast(ParsedFeed, feedparser.parse(raw_bytes))


def classify_parse_outcome(parsed: ParsedFeed) -> PollErrorCode | None:
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
