import logging
from dataclasses import dataclass

from feed_commons.errors import PollError
from feed_commons.fetch import fetch_feed_bytes
from feed_commons.normalize import NormalizedItem, normalize_entry
from feed_commons.parse import classify_parse_outcome, parse_feed

# The CLI (cli.py) hardcodes these same two values when it calls _run_poll
# directly (it can't use poll()'s own defaults since it needs the
# skipped_count that poll() doesn't return) -- CLI overrides for these are
# out of scope for v1 per requirements.md. Defined here, once, so both
# call sites stay in sync instead of drifting via two independent literals.
DEFAULT_EXCERPT_MAX_LENGTH = 300
DEFAULT_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class _PollOutcome:
    items: list[NormalizedItem]
    skipped_count: int


def _run_poll(url: str, excerpt_max_length: int, timeout_seconds: float) -> _PollOutcome:
    try:
        raw_bytes = fetch_feed_bytes(url, timeout_seconds)

        parsed = parse_feed(raw_bytes)

        error_code = classify_parse_outcome(parsed)
        if error_code is not None:
            raise PollError(error_code)

        items: list[NormalizedItem] = []
        skipped_count = 0
        for entry in parsed.entries:
            normalized = normalize_entry(entry, excerpt_max_length)
            if normalized is None:
                skipped_count += 1
            else:
                items.append(normalized)

        return _PollOutcome(items=items, skipped_count=skipped_count)
    except PollError:
        raise
    except Exception as exc:
        logging.getLogger(__name__).debug("unanticipated exception in _run_poll: %r", exc)
        raise PollError("network_error") from exc


def poll(
    url: str,
    excerpt_max_length: int = DEFAULT_EXCERPT_MAX_LENGTH,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[NormalizedItem]:
    return _run_poll(url, excerpt_max_length, timeout_seconds).items
