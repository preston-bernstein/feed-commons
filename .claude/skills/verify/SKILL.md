---
name: verify
description: How to run this repo's real surface locally — venv setup, and a macOS mutmut fork-crash workaround
---

# feed-commons — local verify recipe

## Environment

Homebrew Python blocks system-wide `pip install` (PEP 668). Use a local venv:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test,dev]"
```

Use `.venv/bin/python3`, `.venv/bin/pytest`, `.venv/bin/ruff`, `.venv/bin/mutmut` —
never the bare system `python3`/`pytest` (they won't have `feed_commons` or its
dependencies installed).

## Running the test suite + lint (what CI runs)

```bash
.venv/bin/pytest -m "not network"
.venv/bin/ruff check .
```

## Running mutation testing (mutmut) on macOS

`mutmut run` with its default multiprocessing worker pool crashes on macOS —
`requests`' proxy-detection code (`_scproxy`) calls into a CoreFoundation API
(`SCDynamicStoreCopyProxiesWithOptions`) that isn't fork-safe, so a forked
mutmut worker process segfaults mid-run. Symptom: many mutants come back
`segfault` instead of `killed`/`survived`, alongside a `fatal error` C
traceback ending in `_scproxy.get_proxy_settings`. This isn't a code
problem — it's the same class of fork+CoreFoundation crash `scraper-commons`
hit with its own multiprocess test tooling.

Fix: force a single worker (no fork) and disable macOS's fork-safety abort:

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
export no_proxy='*'
rm -rf mutants/ .mutmut-cache   # clear any cache poisoned by a prior segfaulted run
.venv/bin/mutmut run --max-children 1
.venv/bin/mutmut results
```

`--max-children 1` is the load-bearing flag — it disables mutmut's process
pool entirely, so nothing forks. It's slower (no parallelism) but reliable.
Always clear `mutants/`/`.mutmut-cache` before a run you intend to trust —
mutmut's cache is keyed by source hash and can silently replay stale
(including segfaulted) results across runs, especially after a `pyproject.toml`
change it can't track for behavioral impact.

`mutmut show <mutant-id>` prints the exact code-change diff for any
survived/segfaulted mutant — use it to see precisely what wasn't caught
before writing a test to catch it.

## Gotcha: monkeypatching `validate_https_url` hides mutations

`pytest-httpserver` only serves plain HTTP, but `fetch_feed_bytes` rejects
non-`https` URLs. Tests that need a real local server therefore monkeypatch
`feed_commons.fetch.validate_https_url` to a no-op. A true no-op ignores its
argument — so any mutation that corrupts the URL passed into that call
becomes invisible to mutation testing. Where argument-passing correctness at
that call site matters, prefer mocking `requests.get` directly instead (with
a real `https://...` string) so the real, unpatched `validate_https_url`
stays in the loop. See `tests/test_fetch.py` for the pattern.
