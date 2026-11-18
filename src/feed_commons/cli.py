import argparse
import json
import sys

from feed_commons.errors import PollError
from feed_commons.poll import (
    DEFAULT_EXCERPT_MAX_LENGTH,
    DEFAULT_TIMEOUT_SECONDS,
    _run_poll,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="feed_commons")
    subparsers = parser.add_subparsers(dest="command", required=True)

    poll_parser = subparsers.add_parser(
        "poll", help="poll a feed URL and print normalized items as JSON"
    )
    poll_parser.add_argument("url", help="the feed URL to poll")
    # Accepted but currently always-on: output is always JSON regardless of whether
    # this flag is passed. Reserved for a possible future non-JSON output mode.
    poll_parser.add_argument("--json", action="store_true", help="output as JSON (always on)")

    return parser


def _write_result(envelope: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(envelope) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        outcome = _run_poll(args.url, DEFAULT_EXCERPT_MAX_LENGTH, DEFAULT_TIMEOUT_SECONDS)
    except PollError as e:
        envelope: dict[str, object] = {"status": "fail", "items": [], "error": e.code}
        _write_result(envelope)
        return 1

    degraded = outcome.skipped_count > 0
    envelope = {
        "status": "degraded" if degraded else "ok",
        "items": outcome.items,
        "error": None,
    }
    _write_result(envelope)
    return 0
