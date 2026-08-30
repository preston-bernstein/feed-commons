# Tasks: `poll` submodule

Generated from: docs/poll-submodule/ on 2026-08-15

## Status legend
- [ ] pending
- [>] in progress
- [x] done
- [!] blocked

## Tasks

### Task 1: Create `errors.py` — error types and taxonomy
**Status**: [x] done
**Files**: src/feed_commons/errors.py
**Test**: Run `python -c "from feed_commons.errors import PollError, PollErrorCode; e = PollError('timeout'); assert str(e) == 'timeout'"` to verify the error stringifies to just the code.
**Depends on**: none
**Parallelizable**: No
**Notes**:

### Task 2: Create `normalize.py` — normalization functions
**Status**: [x] done
**Files**: src/feed_commons/normalize.py
**Test**: Import the module and verify TypedDict shape: `from feed_commons.normalize import NormalizedItem; assert NormalizedItem.__annotations__.keys() == {'title', 'link', 'guid', 'pub_date', 'description_excerpt'}`. No network calls needed.
**Depends on**: Task 1 (errors.py)
**Parallelizable**: Yes
**Notes**:

### Task 3: Create `tests/test_normalize.py` — normalization unit tests
**Status**: [x] done
**Files**: tests/test_normalize.py
**Test**: Run `pytest tests/test_normalize.py -v` with zero network calls; all tests pass, including a non-zero-UTC-offset pub_date test.
**Depends on**: Task 2 (normalize.py)
**Parallelizable**: Yes
**Notes**:

### Task 4: Create `fetch.py` — URL validation and HTTP fetch
**Status**: [x] done
**Files**: src/feed_commons/fetch.py
**Test**: Run `python -c "from feed_commons.fetch import validate_https_url; validate_https_url('http://example.com')"` and expect `PollError('invalid_url')` to be raised. Import succeeds if no syntax errors.
**Depends on**: Task 1 (errors.py)
**Parallelizable**: Yes
**Notes**:

### Task 5: Create `tests/test_fetch.py` — fetch and validation tests
**Status**: [x] done
**Files**: tests/test_fetch.py
**Test**: Run `pytest tests/test_fetch.py -v -m "not network"` and all tests pass, including a no-credential-headers assertion.
**Depends on**: Task 4 (fetch.py)
**Parallelizable**: Yes
**Notes**:

### Task 6: Create `parse.py` — feed parsing and bozo classification
**Status**: [x] done
**Files**: src/feed_commons/parse.py
**Test**: Import and run `from feed_commons.parse import parse_feed; result = parse_feed(b'<rss><channel><item><title>Test</title></item></channel></rss>'); assert result.entries` to verify basic parsing works.
**Depends on**: Task 1 (errors.py)
**Parallelizable**: Yes
**Notes**:

### Task 7: Create `tests/test_parse.py` — parse and bozo classification tests
**Status**: [x] done
**Files**: tests/test_parse.py
**Test**: Run `pytest tests/test_parse.py -v` with zero network calls; all tests pass.
**Depends on**: Task 6 (parse.py)
**Parallelizable**: Yes
**Notes**:

### Task 8: Create `poll.py` — orchestration and public API
**Status**: [x] done
**Files**: src/feed_commons/poll.py
**Test**: Run `python -c "from feed_commons.poll import poll; from feed_commons.errors import PollError; assert callable(poll)"` to verify the module loads.
**Depends on**: Task 2 (normalize.py), Task 4 (fetch.py), Task 6 (parse.py)
**Parallelizable**: No
**Notes**:

### Task 9: Create `tests/test_poll.py` — end-to-end orchestration tests
**Status**: [x] done
**Files**: tests/test_poll.py
**Test**: Run `pytest tests/test_poll.py -v` with zero network calls; all tests pass, including catch-all/re-raise coverage.
**Depends on**: Task 8 (poll.py)
**Parallelizable**: Yes
**Notes**:

### Task 10: Create `cli.py` and `__main__.py` — CLI + entry point
**Status**: [x] done
**Files**: src/feed_commons/cli.py, src/feed_commons/__main__.py
**Test**: Run `python -c "from feed_commons.cli import main; assert callable(main)"` and `python -m feed_commons --help` with no errors.
**Depends on**: Task 8 (poll.py)
**Parallelizable**: Yes
**Notes**:

### Task 11: Create `tests/test_cli.py` — CLI output and exit-code tests
**Status**: [x] done
**Files**: tests/test_cli.py
**Test**: Run `pytest tests/test_cli.py -v` with zero network calls; all tests pass, including a subprocess-level `python -m feed_commons poll <url> --json` test.
**Depends on**: Task 10 (cli.py)
**Parallelizable**: Yes
**Notes**:

### Task 12: Modify `__init__.py` — public API exports
**Status**: [x] done
**Files**: src/feed_commons/__init__.py
**Test**: Run `python -c "from feed_commons import poll, PollError, PollErrorCode; assert callable(poll)"`.
**Depends on**: Task 1 (errors.py), Task 8 (poll.py)
**Parallelizable**: No
**Notes**:

### Task 13: Finalize — full test suite + lint
**Status**: [x] done
**Files**: (verification-only)
**Test**: `pytest -m "not network"` (full tests/ dir, zero failures), then `ruff check .` (zero violations).
**Depends on**: Task 12 (__init__.py)
**Parallelizable**: No
**Notes**:

## Blocked / open
(none yet)
