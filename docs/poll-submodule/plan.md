# Plan: `poll` submodule

## Approach
Split the extracted-from-`bulletin-poll.ts` logic into four small, independently-testable
layers — URL validation + HTTP fetch, feed parsing + bozo classification, per-item
normalization, and orchestration — mirroring the reference implementation's own separation
of `stripHtmlAndTruncate`/`resolveGuid`/`normalizePubDate`/`classifyFetchError` as pure
functions plus one orchestrating entry point. `poll()` stays a single stateless function
(CONTRACT.md rule 2) with no class, no session object, and no I/O beyond one `requests.get`
call, so it fits the "pure fetch → parse → normalize → return" contract exactly. The CLI is
a thin wrapper that calls a slightly richer internal orchestration function (not the public
`poll()` itself) so it can compute `ok`/`degraded` from a skipped-item count that
the public API's minimal return type deliberately doesn't expose. Item validity itself is
drop-not-flag, matching the reference TS implementation's `isValidItem`: an entry with an
empty title or empty resolved link is simply excluded from the result rather than carried
through with issue flags attached.

## Architecture

```
python -m feed_commons poll <url> --json
            │
            ▼
      __main__.py ──▶ cli.py: main()
                          │
                          ▼
                    poll.py: _run_poll()  ◀── (private, richer than public poll())
                     │        │        │
                     ▼        ▼        ▼
                fetch.py   parse.py  normalize.py
                (validate   (feedparser  (strip_html_and_truncate,
                 URL, HTTP   wrapper +    resolve_guid,
                 fetch,      bozo/bozo_   normalize_pub_date,
                 exception   exception    normalize_entry -> Item|None)
                 classify)  classify)
                     │        │        │
                     └────────┴────────┘
                          │
                          ▼
                    errors.py: PollError(code)
                    (raised on any failure path,
                     caught at _run_poll's boundary)

from feed_commons import poll   ──▶  poll.py: poll()  ──▶  _run_poll() ──▶ .items only
                                      (public API, raises PollError on failure)
```

Both the public `poll()` and the CLI call the same private `_run_poll()` in `poll.py`.
`_run_poll()` returns a small internal `_PollOutcome(items: list[NormalizedItem],
skipped_count: int)`; it never crosses the public boundary. `poll()` unwraps
`_PollOutcome.items` and returns that list, or lets `PollError` propagate. The CLI reads
`items` and `skipped_count` and computes `degraded = skipped_count > 0` to decide `ok` vs
`degraded`, and catches `PollError` for `fail`. This is the one deliberate layering decision
not obvious from the requirements doc: FR1/AC6 fix `poll()`'s success return type as *just*
a list of normalized items, but the CLI still needs to know whether any entries were
dropped as invalid (empty title or empty resolved link) — a count the public 5-field item
shape has no room to carry. Without this split, the CLI would have to re-fetch/re-parse to
recover that count. Item validity itself is drop-not-flag (see Integration points /
`normalize.py`): there is no per-item issue metadata to carry, only a count of how many
entries `normalize_entry` returned `None` for.

## Data model
No data model changes. `poll` is stateless per CONTRACT.md rule 2 — no tables, no on-disk
cache, no schema. The only "data model" is the in-memory normalized-item shape, addressed
below.

**Item type choice: `TypedDict`, not a dataclass or plain dict.** `NormalizedItem` is
defined as a `TypedDict` in `normalize.py` with keys `title`, `link`, `guid`, `pub_date`,
`description_excerpt`. Rationale: the CLI must `json.dumps()` these items directly with no
conversion step (a dataclass would need `dataclasses.asdict()` or a custom encoder first),
while a plain `dict` gives Python callers no static shape at all — `TypedDict` is a normal
dict at runtime (zero overhead, trivially JSON-serializable) but gives `from feed_commons
import poll` callers type-checked field access.

## API / interface contract

**Python API** (`src/feed_commons/__init__.py` re-exports):
```python
from feed_commons import poll, PollError

items: list[NormalizedItem] = poll(url, excerpt_max_length=300, timeout_seconds=15)
# raises PollError with .code in
# {"timeout", "invalid_url", "http_error", "parse_error", "network_error"}
```
`NormalizedItem` (TypedDict): `title: str`, `link: str`, `guid: str`,
`pub_date: str | None`, `description_excerpt: str`.

**CLI**: `python -m feed_commons poll <url> [--json]`
- `--json` is accepted (argparse `store_true`) but output is always JSON — no other output
  format is specified by any FR, so no unbuilt text-mode branch is added; the flag exists
  only to match the documented invocation shape (FR21).
- stdout: exactly one JSON object, always terminated by `\n` from `print()`:
  - success, `skipped_count == 0`: `{"status": "ok", "items": [...], "error": null}`, exit 0
  - success, `skipped_count > 0` (≥1 entry dropped for an empty title or empty resolved
    link): `{"status": "degraded", "items": [...], "error": null}`, exit 0
  - classified failure: `{"status": "fail", "items": [], "error": "<one of 5 codes>"}`, exit 1
- No flags for `excerpt_max_length` / `timeout_seconds` — not required by any FR; CLI uses
  `poll()`'s defaults (300, 15s). Adding flags for these would be speculative beyond what's
  asked.

**Error taxonomy** (`errors.py`): `PollErrorCode = Literal["timeout", "invalid_url",
"http_error", "parse_error", "network_error"]`; `class PollError(Exception)` carries `.code`
and stringifies to just the code — never a wrapped exception message (design rule 4 /
FR11 / FR17).

## Integration points
- `src/feed_commons/errors.py` (new) — `PollErrorCode` literal, `PollError` exception
  class carrying only `.code`, never the original exception's message/args.
- `src/feed_commons/normalize.py` (new) — `NormalizedItem` TypedDict; pure functions
  `strip_html_and_truncate`, `resolve_guid`, `normalize_pub_date`, `extract_description`,
  and `normalize_entry(entry, excerpt_max_length) -> NormalizedItem | None` — no separate
  `ItemIssues` type. Item validity is drop-not-flag, matching the reference TS
  implementation's `isValidItem`: `normalize_entry` returns `None` when the entry's title or
  resolved link is empty, and a fully-populated `NormalizedItem` otherwise. Field-source
  specifics (correcting the naive 1:1 port from `bulletin-poll.ts`'s `RawBulletinItem`
  shape onto `feedparser`'s entry dict):
  - `resolve_guid` reads `entry.get('id')`, not `entry.get('guid')` — feedparser normalizes
    both RSS `<guid>` and Atom `<id>` onto `entry.id`, so `entry.get('guid')` is frequently
    absent.
  - `extract_description` precedence: `entry.content[0].value` if `entry.get('content')` is
    a non-empty list, else `entry.get('summary', '')` (feedparser aliases RSS
    `<description>` to `summary`), else `''`.
  - `normalize_pub_date` fallback: try `entry.get('published_parsed')` first, then
    `entry.get('updated_parsed')` if absent (Atom-only-`<updated>` feeds). Convert the
    resulting UTC `struct_time` via `calendar.timegm(struct_time)` → unix timestamp →
    `datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()` — never `time.mktime`, which
    interprets the `struct_time` as local time and silently shifts every `pub_date` by the
    machine's UTC offset (dangerous because CI runners default to UTC and won't catch this
    bug in a typical assertion, so the wrong implementation ships green).
- `src/feed_commons/fetch.py` (new) — `validate_https_url(url) -> None` (raises
  `PollError("invalid_url")`, pure string parsing via `urllib.parse.urlsplit`, no network
  call, runs before any fetch per FR2/FR3). `urlsplit` almost never raises on garbage input,
  so validation explicitly checks the parsed result has a non-empty `netloc` (host) in
  addition to `scheme == 'https'` — without this, `https://` or `https:///path` (empty
  host) would pass validation and reach `requests.get`, producing a less-clean downstream
  failure instead of a clean `invalid_url`.
  `fetch_feed_bytes(url, timeout_seconds) -> bytes` calls
  `requests.get(url, timeout=timeout_seconds, allow_redirects=False, stream=True,
  headers={"User-Agent": "feed-commons/<version> (+https://github.com/preston-bernstein/
  feed-commons)"})`:
  - `allow_redirects=False` — a 3xx response then flows through the existing non-2xx →
    `http_error` rule automatically, no new error code needed. This closes a real gap:
    `requests` follows redirects by default, so an `https://` feed 301-ing to an `http://`
    URL would otherwise silently defeat HTTPS-only enforcement.
  - explicit `User-Agent` — standard feed-reader etiquette, not anti-bot evasion; prevents
    legitimate feed hosts that reject the bare default `python-requests/x.y` UA from being
    misdiagnosed as needing scraper-commons.
  - `stream=True` plus a 10 MB response-size cap enforced while reading (checking
    `Content-Length` when present, and/or counting bytes read and aborting past the cap) —
    an oversized response is classified `http_error`.
  - exception classification order matters: `requests.exceptions.ConnectTimeout` is a
    subclass of *both* `ConnectionError` and `Timeout` (multiple inheritance in `requests`'
    exception hierarchy), so the classifier checks `Timeout`-family exceptions
    (`ConnectTimeout`, `ReadTimeout`, or the base `Timeout`) *before* the generic
    `ConnectionError` check — otherwise a connection-phase timeout misclassifies as
    `network_error` instead of `timeout`. `requests.exceptions.ConnectionError`/other
    `RequestException` → `network_error`; non-2xx response status → `http_error`.
- `src/feed_commons/parse.py` (new) — `parse_feed(raw_bytes) -> feedparser.FeedParserDict`
  wrapping `feedparser.parse`; `classify_parse_outcome(parsed) -> PollErrorCode | None`
  implementing FR9/FR10's bozo/bozo_exception/entry-count logic against an explicit
  `BENIGN_BOZO_EXCEPTIONS` allowlist (`feedparser.exceptions.CharacterEncodingOverride`,
  `feedparser.exceptions.NonXMLContentType`) imported from `feedparser.exceptions`
  (feedparser ≥6.0.11, matching the pin in `pyproject.toml`). Completes the bozo/
  bozo_exception truth table with the previously-unhandled case: `bozo == 1` with
  `bozo_exception is None` is its own explicit branch, classified by entry count alone —
  zero entries → `parse_error`, one or more entries → not an error.
- `src/feed_commons/poll.py` (new) — private `_PollOutcome` dataclass (`items:
  list[NormalizedItem]`, `skipped_count: int` — a count of entries `normalize_entry`
  returned `None` for, not a `degraded: bool` and not per-item issue flags), private
  `_run_poll(url, excerpt_max_length, timeout_seconds) -> _PollOutcome` orchestrating
  validate → fetch → parse → classify → normalize. `_run_poll`'s top-level exception
  handling is ordered `except PollError: raise` *before* the generic `except Exception`
  fallback — without that ordering, a naive `try/except Exception` catches `PollError` too
  (it's an `Exception` subclass) and reclassifies every specific code (`timeout`,
  `http_error`, `invalid_url`, `parse_error`) down to a generic `network_error`, destroying
  the taxonomy. Only a genuinely unanticipated exception reaches the catch-all, which logs
  its type and a truncated repr via `logging.getLogger(__name__).debug(...)` before mapping
  it to `network_error` (mirrors `classifyFetchError`'s default-case fallback in
  `bulletin-poll.ts`, satisfying FR20) — this preserves the bounded-code contract toward
  callers (design rule 4) while giving operators a diagnostic trail, so a masked internal
  bug in this codebase's own logic doesn't get silently misattributed to "the network is
  flaky" with zero way to tell the difference. Public `poll(url, excerpt_max_length=300,
  timeout_seconds=15) -> list[NormalizedItem]` unwrapping `_run_poll(...).items`.
- `src/feed_commons/cli.py` (new) — argparse parser with a `poll` subcommand (`url`
  positional, `--json` flag), calls `_run_poll`, computes `degraded = skipped_count > 0`,
  builds the `{"status", "items", "error"}` envelope, returns the process exit code; no
  logging/print side effects beyond the one JSON line. The `--json` flag is accepted but
  currently always-on (output is always JSON regardless) — a one-line code comment at its
  `argparse` definition states it's reserved for a possible future non-JSON output mode, so
  a future maintainer doesn't mistake the dead flag for an oversight.
- `src/feed_commons/__main__.py` (new) — `sys.exit(cli.main())`, the `python -m
  feed_commons` entry point.
- `src/feed_commons/__init__.py` (modify) — replace the scaffold docstring-only stub with
  `from feed_commons.poll import poll` and `from feed_commons.errors import PollError,
  PollErrorCode`, plus `__all__`.
- `tests/test_normalize.py` (new) — unit tests for FR13–19 / AC7–10 against synthetic
  feedparser entry dicts (no network, no `pytest-httpserver` needed).
- `tests/test_fetch.py` (new) — `pytest-httpserver`-backed tests for FR2–7 / AC1–5:
  invalid scheme/malformed URL (no server interaction), a slow-responding handler for
  timeout, a 404/500 handler for `http_error`, and a bound-then-closed socket for
  `network_error` (connection refused, the closest reliable local proxy for "connection
  reset" available without raw socket manipulation).
- `tests/test_parse.py` (new) — FR8–10 / AC11–12 against a malformed-XML fixture string and
  a benign-`bozo_exception` fixture string (e.g. wrong `Content-Type` triggering
  `NonXMLContentType`).
- `tests/test_poll.py` (new) — end-to-end wiring tests via `pytest-httpserver` covering
  AC6, AC13, plus the `skipped_count` interaction between `normalize.py`'s drop-not-flag
  `normalize_entry` and `poll.py`'s `_PollOutcome`.
- `tests/test_cli.py` (new) — FR21–26 / AC14–16 by invoking `cli.main()` directly (not a
  subprocess) against a `pytest-httpserver` fixture, asserting the printed JSON shape and
  returned exit code.
- No changes to `pyproject.toml` — `requests`/`feedparser`/`pytest`/`pytest-httpserver`/
  `ruff` are already declared at the versions this plan targets; no `[project.scripts]`
  entry is needed since the CLI is invoked via `python -m feed_commons`, not a console
  script.

## Technology choices
- **`urllib.parse.urlsplit`** for URL validation (stdlib, already implicitly available) —
  pure syntactic check with no side effects, run before `requests` ever touches the
  network, satisfying FR2/FR3's "before attempting any network fetch" ordering.
- **`feedparser`'s own `published_parsed`/`updated_parsed` `struct_time`** (already
  produced by `feedparser.parse`) instead of hand-parsing the raw `pubDate` string —
  `feedparser` already normalizes RFC-822, W3C-DTF, and other feed date formats into UTC
  for us; re-parsing the raw string in Python would re-derive logic `feedparser` already
  proved. `normalize_pub_date` falls back from `published_parsed` to `updated_parsed`
  (Atom-only-`<updated>` feeds) and, when neither is present, returns `None` — a missing or
  unparseable date is never grounds to drop an item (drop-not-flag validity is title/link
  only, per Data model / Integration points) and never affects the CLI's `degraded` signal,
  which is driven purely by `skipped_count`.
- **`feedparser.exceptions.{CharacterEncodingOverride,NonXMLContentType}`** as an explicit
  benign-exception allowlist (rather than a denylist of "malformed" types) — an allowlist
  fails closed: an unrecognized future `bozo_exception` type defaults to `parse_error`
  rather than silently passing through, which matches design rule 4's bias toward bounded,
  conservative error classification.

## Risk areas
- **bozo/bozo_exception classification correctness.** FR9/FR10's benign-vs-malformed split
  depends on `feedparser.exceptions` class identity being stable at the pinned `>=6.0.11,<7`
  range. The `bozo == 1` / `bozo_exception is None` case is now handled as its own explicit
  branch (classify by entry count alone — zero entries → `parse_error`, one or more → not
  an error), closing the previous gap in the truth table, but the classifier still needs
  verification against real fixture strings, not just the two named benign-exception
  examples in the requirements doc.
- **requests exception hierarchy edge cases.** `ConnectionError`/`Timeout`/generic
  `RequestException` don't cleanly separate every real-world transport fault — e.g. a
  connection that resets mid-body-read can surface as `ChunkedEncodingError` (a
  `RequestException` subclass, not `ConnectionError`) rather than the exception type this
  plan's classifier expects; the `fetch.py` classifier needs a catch-all
  `RequestException` → `network_error` branch (already planned) to avoid a gap turning
  into an unclassified/uncaught exception (FR20).
- **Testing "connection reset" and "timeout" without a real network call.** `pytest-httpserver`
  doesn't natively simulate a mid-response reset; the plan's bind-then-close-socket
  approach for `network_error` and a slow-handler approach for `timeout` are the standard
  workarounds but need to be verified they actually produce the intended `requests`
  exception type rather than, say, an immediate `ConnectionRefusedError` on some platforms
  vs. a hang.
- **pub_date instant equivalence (AC9).** Converting `feedparser`'s UTC `struct_time` back
  to an ISO-8601 string that's "equal to the same instant" as the source RFC-822 string
  requires correct UTC-aware conversion (`calendar.timegm` + `datetime.fromtimestamp(...,
  tz=UTC)`, not `time.mktime`, which is local-time-based) — an easy off-by-timezone bug if
  implemented carelessly.
- **`_run_poll`/`poll()` layering is a design choice not explicit in requirements.md.**
  Nothing in the requirements doc mandates the private-outcome-object split described in
  Architecture; it's inferred from the CLI needing a `skipped_count` that FR1/AC6 don't put
  in `poll()`'s public return type. An implementer could instead have the CLI re-derive
  degraded status by re-inspecting `NormalizedItem`s alone, which has no way to recover how
  many entries were dropped as invalid — so this layering (an internal `_PollOutcome`
  carrying `items` + `skipped_count`, never crossing the public boundary) should be treated
  as load-bearing, not optional, during implementation.
- **`poll()`'s public return type is a deliberate, considered trade-off, not an oversight.**
  It's locked to `list[NormalizedItem]` now, before any real Python caller exists beyond the
  CLI. This is accepted as simplicity-now over speculative flexibility: a future Python
  caller that needs degraded-item information (e.g. `skipped_count`) will require a new
  function or a breaking signature change to `poll()`, not a silent extension of the
  existing return shape.
- **The fixed 5-code error taxonomy is a forward-compatibility constraint for consumers.**
  CONTRACT.md design rule 4 closes the taxonomy at `{"timeout", "invalid_url", "http_error",
  "parse_error", "network_error"}`. Non-Python consumers doing exhaustive matching against
  exactly these 5 strings will need a coordinated update if a 6th code is ever added — a
  known, accepted constraint of the current design, not addressed further in v1.
