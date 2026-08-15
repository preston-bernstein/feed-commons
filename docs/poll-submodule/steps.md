# Steps: `poll` submodule

## Prerequisites
- Git hooks installed per the repo's CLAUDE.md (run `scripts/install-hooks.sh` if not already done).
- Run `pip install -e .` (or equivalent editable install) so `python -m feed_commons` resolves locally — CI already does this via `pip install -e ".[test,dev]"`, but a developer working through these steps manually needs it too, especially by the CLI-testing steps.
- The codebase has `requests`, `feedparser`, `pytest`, and `pytest-httpserver` already declared in `pyproject.toml`.

## Implementation steps

### Step 1: Create `errors.py` — error types and taxonomy
**What**: Define the `PollErrorCode` literal type and `PollError` exception class carrying only the bounded error code (never raw exception messages or stack traces).
**Files**: `src/feed_commons/errors.py`
**Test**: Run `python -c "from feed_commons.errors import PollError, PollErrorCode; e = PollError('timeout'); assert str(e) == 'timeout'"` to verify the error stringifies to just the code.
**Depends on**: none
**Parallelizable**: No

### Step 2: Create `normalize.py` — normalization functions
**What**: Implement `NormalizedItem` TypedDict, `strip_html_and_truncate()`, `resolve_guid()`, `normalize_pub_date()`, `extract_description()`, and `normalize_entry()` to convert feedparser entry dicts to normalized items. `normalize_entry()` returns `NormalizedItem | None`, returning None when title or resolved link is empty — the whole entry is skipped, not flagged.
**Files**: `src/feed_commons/normalize.py`
**Test**: Import the module and verify TypedDict shape: `from feed_commons.normalize import NormalizedItem; assert NormalizedItem.__annotations__.keys() == {'title', 'link', 'guid', 'pub_date', 'description_excerpt'}`. No network calls needed.
**Depends on**: Step 1 (errors.py)
**Parallelizable**: Yes

### Step 3: Create `tests/test_normalize.py` — normalization unit tests
**What**: Test `normalize.py` functions against synthetic feedparser entry dicts covering FR13–19 (AC7–10): HTML stripping and truncation, guid fallback to link, pubDate parsing to ISO-8601 or null, missing description, missing/empty title detection.
**Files**: `tests/test_normalize.py`
**Test**: Run `pytest tests/test_normalize.py -v` with zero network calls; all tests pass. Include an explicit test case for pub_date conversion with a non-zero UTC offset (e.g. `Wed, 02 Oct 2024 15:00:00 -0700`) and assert the exact resulting ISO-8601 instant — this is the only way to catch a `time.mktime`-vs-`calendar.timegm` regression, since CI runners default to UTC and a same-timezone test wouldn't catch the bug.
**Depends on**: Step 2 (normalize.py)
**Parallelizable**: Yes

### Step 4: Create `fetch.py` — URL validation and HTTP fetch
**What**: Implement `validate_https_url(url)` to reject non-https schemes and URLs with an empty host/netloc before any network call (FR2, FR3), and `fetch_feed_bytes(url, timeout_seconds)` wrapping `requests.get(url, timeout=timeout_seconds, allow_redirects=False, stream=True, headers={"User-Agent": "feed-commons/<version> (+https://github.com/preston-bernstein/feed-commons)"})` — `allow_redirects=False` so a 3xx response flows through the non-2xx → `http_error` path (FR5); a 10 MB response-size cap enforced while streaming, oversized → `http_error`; exception classification checks `Timeout`-family exceptions (`ConnectTimeout`, `ReadTimeout`) BEFORE generic `ConnectionError`, since `ConnectTimeout` subclasses both → `timeout` vs `network_error`; other `RequestException` → `network_error`; non-2xx status → `http_error` (FR6–8).
**Files**: `src/feed_commons/fetch.py`
**Test**: Run `python -c "from feed_commons.fetch import validate_https_url; validate_https_url('http://example.com')"` and expect `PollError('invalid_url')` to be raised. Import succeeds if no syntax errors.
**Depends on**: Step 1 (errors.py)
**Parallelizable**: Yes

### Step 5: Create `tests/test_fetch.py` — fetch and validation tests
**What**: Use `pytest-httpserver` fixtures to test FR2–7 (AC1–5): invalid scheme/malformed URL (no server), timeout via slow handler, 404/500 responses, and connection-refused error. Verify no network calls escape the mocked environment.
**Files**: `tests/test_fetch.py`
**Test**: Run `pytest tests/test_fetch.py -v -m "not network"` and all tests pass; inspect code to confirm all HTTP interactions are via `pytest-httpserver`, not real endpoints. Include an assertion verifying no auth/credential headers are attached to outbound requests (inspect the request `pytest-httpserver` received).
**Depends on**: Step 4 (fetch.py)
**Parallelizable**: Yes

### Step 6: Create `parse.py` — feed parsing and bozo classification
**What**: Implement `parse_feed(raw_bytes)` wrapping `feedparser.parse`, and `classify_parse_outcome(parsed)` implementing FR8–10 bozo classification logic: return None for success, `parse_error` only when `bozo == 1` with zero entries or a malformed-document exception (allowlisting `CharacterEncodingOverride` and `NonXMLContentType` as benign per FR10).
**Files**: `src/feed_commons/parse.py`
**Test**: Import and run `from feed_commons.parse import parse_feed; result = parse_feed(b'<rss><channel><item><title>Test</title></item></channel></rss>'); assert result.entries` to verify basic parsing works.
**Depends on**: Step 1 (errors.py)
**Parallelizable**: Yes

### Step 7: Create `tests/test_parse.py` — parse and bozo classification tests
**What**: Test `parse_feed()` and `classify_parse_outcome()` against fixture strings covering FR8–10 (AC11–12): well-formed RSS/Atom, malformed XML with zero entries (expect `parse_error`), and benign bozo exception with ≥1 entry (expect no error).
**Files**: `tests/test_parse.py`
**Test**: Run `pytest tests/test_parse.py -v` with zero network calls; all tests pass.
**Depends on**: Step 6 (parse.py)
**Parallelizable**: Yes

### Step 8: Create `poll.py` — orchestration and public API
**What**: Define private `_PollOutcome` dataclass (`items: list[NormalizedItem]`, `skipped_count: int` — a count of entries `normalize_entry` returned `None` for), private `_run_poll(url, excerpt_max_length, timeout_seconds)` orchestrating validate → fetch → parse → classify → normalize, with `except PollError: raise` BEFORE a generic `except Exception` fallback that logs the real exception (`logging.getLogger(__name__).debug(...)`) then maps it to `network_error` (FR20) — the ordering matters so a lower layer's already-classified error is never reclassified. Public `poll(url, excerpt_max_length=300, timeout_seconds=15)` unwraps `_run_poll().items` or lets `PollError` propagate.
**Files**: `src/feed_commons/poll.py`
**Test**: Run `python -c "from feed_commons.poll import poll; from feed_commons.errors import PollError; assert callable(poll)"` to verify the module loads and `poll` is importable from submodules.
**Depends on**: Step 2 (normalize.py), Step 4 (fetch.py), Step 6 (parse.py)
**Parallelizable**: No

### Step 9: Create `tests/test_poll.py` — end-to-end orchestration tests
**What**: Test `poll.py` and the `_run_poll()` internal function via `pytest-httpserver` covering AC6 (successful feed fetch and parse returns normalized items), AC13 (no real network calls), and the `skipped_count` interaction between `normalize.py`'s drop-not-flag `normalize_entry` and `poll.py`'s `_PollOutcome`. Include tests for catch-all/re-raise behavior: (a) unanticipated internal exceptions raised during orchestration map to `network_error` and don't propagate raw, and (b) a `PollError` already raised by a lower layer (e.g. `timeout`) propagates out of `poll()`/`_run_poll()` unchanged — NOT reclassified as `network_error`.
**Files**: `tests/test_poll.py`
**Test**: Run `pytest tests/test_poll.py -v` with zero network calls; all tests pass.
**Depends on**: Step 8 (poll.py)
**Parallelizable**: Yes

### Step 10: Create `cli.py` and `__main__.py` — CLI argument parsing, output formatting, and package entry point
**What**: Implement argparse parser in `cli.py` with `poll` subcommand (url positional, optional --json flag), invoke `_run_poll()` from `poll.py`, build the `{"status": "ok"|"degraded"|"fail", "items": [...], "error": ...}` JSON envelope (FR21–26), compute ok vs degraded from issue flags, and return the appropriate exit code. Implement `__main__.py` as a one-line entry point: `sys.exit(cli.main())`, enabling `python -m feed_commons poll <url> --json` invocation.
**Files**: `src/feed_commons/cli.py`, `src/feed_commons/__main__.py`
**Test**: Run `python -c "from feed_commons.cli import main; assert callable(main)"` to verify cli.py loads, and `python -m feed_commons --help` to verify the help text appears with no errors.
**Depends on**: Step 8 (poll.py)
**Parallelizable**: Yes

### Step 11: Create `tests/test_cli.py` — CLI output and exit-code tests
**What**: Test CLI output (FR21–26, AC14–16) by invoking `cli.main()` directly against `pytest-httpserver` fixtures, asserting JSON shape and exit codes for ok (no issues), degraded (≥1 item with missing title or unparseable pub-date), and fail (HTTP error, timeout, parse error) scenarios. Additionally, add subprocess-level tests that run the CLI as a real subprocess (`subprocess.run([sys.executable, "-m", "feed_commons", "poll", url, "--json"], ...)`) against `pytest-httpserver` fixtures and assert the printed JSON and exit code — a genuine end-to-end check, not just in-process.
**Files**: `tests/test_cli.py`
**Test**: Run `pytest tests/test_cli.py -v` with zero network calls; all tests pass.
**Depends on**: Step 10 (cli.py)
**Parallelizable**: Yes

### Step 12: Modify `__init__.py` — public API exports
**What**: Replace the scaffold docstring stub with explicit imports: `from feed_commons.poll import poll`, `from feed_commons.errors import PollError, PollErrorCode`, and define `__all__` listing all public symbols.
**Files**: `src/feed_commons/__init__.py`
**Test**: Run `python -c "from feed_commons import poll, PollError, PollErrorCode; assert callable(poll)"` to verify the public API is importable and type annotations are available for callers.
**Depends on**: Step 1 (errors.py), Step 8 (poll.py)
**Parallelizable**: No

### Step 13: Finalize: run full test suite + lint
**What**: Run the full test suite and linting pass to verify zero failures and violations (AC13, AC18).
**Files**: (verification-only; covers all prior steps)
**Test**: Run `pytest -m "not network"` against all tests to completion (all tests pass with zero failures), then run `ruff check .` and verify zero linting violations are reported for all poll submodule code.
**Depends on**: Step 12 (__init__.py)
**Parallelizable**: No

## Rollback plan
All steps are reversible via `git`. Each step writes new files (or modifies `__init__.py`) to isolated paths under `src/feed_commons/` and `tests/`; uncommitting any step via `git reset HEAD <file>` followed by `git checkout <file>` recovers the prior state. The only existing file modified is `__init__.py`, which is safe to revert.
