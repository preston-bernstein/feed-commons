# Requirements: `poll` submodule

## Problem statement
feed-commons exists to give home-lab projects one shared, correctly-tested way to poll a public RSS/Atom feed instead of each project reimplementing fetch/parse/normalize logic. internal-monitor-app already built and shipped this logic once, in TypeScript (`bulletin-poll.ts`), for its New Balance press-release feed. The `poll` submodule is that logic extracted into a stateless, reusable Python function plus a CLI, so internal-monitor-app's normalization rules (HTML-strip-before-truncate, guid-falls-back-to-link, pubDate-parse-or-null, bounded error codes) become available to any Python or non-Python home-lab project without re-deriving them, and without pulling in scraper-commons's stealth/anti-bot machinery, which this problem never needed.

## Users / stakeholders
- Python callers in the home lab that `import feed_commons` directly (e.g. a future internal-monitor-app Python port, or a new project).
- Non-Python callers (e.g. a TypeScript app) that shell out to `python -m feed_commons poll <url> --json` and parse stdout.
- internal-monitor-app, as the reference consumer whose already-shipped `bulletin-poll.ts` behavior this submodule must match.
- feed-commons maintainers relying on CI (`ruff check .`, `pytest -m "not network"`) to gate merges.

## Functional requirements

1. The system shall expose a function `poll(url, excerpt_max_length=300, timeout_seconds=15)` in `src/feed_commons/` importable as `from feed_commons import poll`.
2. The system shall reject any `url` whose scheme is not `https` with an `invalid_url` classification before attempting any network fetch.
3. The system shall reject a `url` that has no non-empty host/netloc component (e.g. `https://` or `https:///path`) with an `invalid_url` classification before attempting any network fetch. Together, FR2 and FR3 define "well-formed URL": a `url` is well-formed only when its scheme is `https` AND it has a non-empty host/netloc; failing either check alone is sufficient for `invalid_url`.
4. The system shall fetch the feed at `url` over HTTPS using `requests`, applying `timeout_seconds` as the request timeout.
5. The system shall NOT follow HTTP redirects automatically when fetching a feed — redirects are disabled at the HTTP client level. Any redirect response (3xx status) is classified via FR7's non-2xx → `http_error` rule rather than being followed. This prevents a feed silently downgrading an `https://` fetch to `http://` via a redirect chain, which would defeat HTTPS-only enforcement (FR2) if redirects were followed blindly.
6. The system shall classify a request that exceeds `timeout_seconds` as `timeout`.
7. The system shall classify an HTTP response with a non-2xx status code as `http_error`.
8. The system shall classify a connection failure (DNS resolution failure, connection refused, TLS failure, or other transport-level fault that is not a timeout) as `network_error`.
9. The system shall parse a successfully-fetched feed body using `feedparser`.
10. The system shall classify a parse outcome as `parse_error` when `feedparser`'s result has `bozo == 1` and zero entries were extracted, or when `bozo_exception` is any exception type other than the benign/survivable allowlist defined in FR11 (i.e. any exception type other than `feedparser.exceptions.CharacterEncodingOverride` or `feedparser.exceptions.NonXMLContentType` is treated as malformed).
11. The system shall NOT classify a parse outcome as `parse_error` when `feedparser` sets `bozo == 1` but still extracts one or more usable entries via a benign/survivable `bozo_exception`. The benign/survivable `bozo_exception` allowlist is exactly `feedparser.exceptions.CharacterEncodingOverride` and `feedparser.exceptions.NonXMLContentType` — no other exception type qualifies.
12. The system shall, when `bozo == 1` and `bozo_exception is None` (an edge case `feedparser` can produce), classify by entry count alone: zero entries is `parse_error`, one or more entries is not an error.
13. The system shall never include a raw exception message, stack trace, or third-party library error string in any value returned to a caller — every failure path returns only one of the five bounded codes: `timeout`, `invalid_url`, `http_error`, `parse_error`, `network_error`.
14. The system shall only produce/include an item for a parsed feed entry when that entry has a non-empty `title` AND a non-empty resolved `link`. An entry that fails this check is skipped entirely — it is not included in `items`, whether as a full item or a partial/flagged one.
15. The system shall, for each parsed feed entry that satisfies FR14, produce a normalized item containing at minimum: `title`, `link`, `guid`, `pub_date`, `description_excerpt`.
16. The system shall read an entry's guid/id value from `feedparser`'s normalized `entry.id` attribute — not a literal `entry.guid` key, which is frequently absent even when a real guid exists. (`feedparser` maps both RSS `<guid>` and Atom `<id>` onto this single `entry.id` field.)
17. The system shall set an item's `guid` to the feed entry's `entry.id` value (per FR16) when present and non-empty (after stripping surrounding whitespace).
18. The system shall set an item's `guid` to the feed entry's `link` value when `entry.id` is absent or empty.
19. The system shall set an item's `guid` to an empty string `""` when both `entry.id` and `link` are absent or empty. In practice, such an entry would already fail the FR14 title/link validity check and be skipped — this requirement holds defensively regardless.
20. The system shall extract an entry's description/content by checking `entry.content` first (a list of content-object dicts; if present and non-empty, use the first entry's `.value`), then falling back to `entry.summary` (`feedparser` aliases RSS `<description>` to `summary`), then to an empty string if neither is present.
21. The system shall strip all HTML markup from an entry's description/content field (per FR20) before truncating it, so a truncation cut never lands mid-tag and never leaves an unstripped tag fragment in the output.
22. The system shall truncate the HTML-stripped description to at most `excerpt_max_length` characters, using the function's `excerpt_max_length` parameter (default 300) as the bound.
23. The system shall extract an entry's publish-date value from `entry.published_parsed` if present, falling back to `entry.updated_parsed` if `published_parsed` is absent (Atom feeds may carry only `<updated>`, no `<published>`).
24. The system shall parse an entry's publish-date field (per FR23) to a canonical ISO-8601 string when the value is present and parses successfully.
25. The system shall set an entry's `pub_date` to `null` (never the raw/invalid date text) when the publish-date field (per FR23) is absent or fails to parse.
26. The system shall never raise an uncaught/unclassified exception out of `poll()` — every reachable failure mode (invalid URL, timeout, HTTP error, parse failure, network failure, and any other exception) is caught and mapped to one of the five bounded codes before returning or raising a classified error. This top-level catch-all shall re-raise an already-classified error (one of the five bounded codes: `timeout`, `invalid_url`, `http_error`, `parse_error`, `network_error`) unchanged — it must NOT catch and reclassify an error that a lower layer already raised, mapping it down to a generic `network_error`. Only a genuinely unanticipated exception type gets mapped to `network_error`.
27. The system shall provide a CLI entry point invocable as `python -m feed_commons poll <url> --json`. The CLI accepts exactly one positional argument (`url`) and one optional flag (`--json`, currently always-on/reserved for a future non-JSON output mode — passing or omitting it does not change output in v1); no other flags are supported.
28. The CLI shall print exactly one JSON object to stdout per invocation, of the shape `{"status": "ok"|"degraded"|"fail", "items": [...], "error": "..."}`.
29. The CLI shall set `"status": "fail"` and populate `"error"` with one of the five bounded codes when `poll()` raises a classified error; `"items"` shall be an empty list in this case.
30. The CLI shall set `"status": "ok"` and omit or null out `"error"` when the feed fetched and parsed successfully and no source entry was skipped for failing the FR14 title/link validity check. Every item in `"items"` has a valid title and link; a null `pub_date` (whether from a feed that supplied no date, or a value that failed to parse per FR25) does not by itself prevent `"status": "ok"`.
31. The CLI shall set `"status": "degraded"` when the feed fetched and parsed successfully but at least one source feed entry was skipped for failing the FR14 title/link validity check. `"items"` shall still contain all successfully normalized (kept) items in this case. A kept item's null `pub_date` is never, on its own, a trigger for `"degraded"`.
32. The CLI shall exit with a non-zero process exit code when `"status": "fail"`, and exit 0 otherwise.

## Non-functional requirements
- HTTP fetch timeout is caller-controlled via `timeout_seconds` (default 15s). The connect phase and the read phase of a single fetch attempt are each bounded by `timeout_seconds`; this is a per-phase bound, not an independently-enforced total-wall-clock cap. This is a documented, accepted characteristic of using a single scalar `requests` timeout, not a defect requiring a new mechanism.
- No credentials, tokens, or auth headers are attached to the outbound fetch (design rule 6 — no credentials in v1).
- No raw exception text, stack trace, response body, or feed URL is written into any returned error value (design rule 4) — bounded codes only.
- `poll()` is stateless: no on-disk cache, no database, no dedupe/seen-guid tracking across calls (design rule 2).
- Fetched response bodies are capped at 10 MB; a response exceeding this cap is classified as `http_error`.
- The outbound fetch sends an explicit, identifiable User-Agent header (not the HTTP client library's bare default) — standard, non-evasive feed-reader identification, distinct from any anti-bot-evasion concern (which remains explicitly out of scope).
- `poll()` accepts any caller-supplied HTTPS URL, including URLs resolving to private/internal network addresses — there is no SSRF-style network-destination filtering in v1. This is an accepted characteristic for the home-lab trusted-caller context this library serves (matching CONTRACT.md's scope discipline); network-destination filtering is a future, explicitly-designed extension if a consumer ever needs to accept untrusted third-party URLs.

## Constraints
- Must use `requests` for HTTP fetch and `feedparser` for parsing — both already declared in `pyproject.toml` dependencies; no other HTTP or feed-parsing library may be substituted.
- Must live under `src/feed_commons/` per the existing Hatchling package layout (`[tool.hatch.build.targets.wheel] packages = ["src/feed_commons"]`).
- Must match the normalization semantics already proven in internal-monitor-app's shipped `packages/core/src/pipeline/bulletin-poll.ts` (`stripHtmlAndTruncate`, `resolveGuid`, `normalizePubDate`) — this submodule generalizes, not redesigns, that behavior.
- Must diverge from internal-monitor-app's error-classification mechanics where the underlying library differs: `feedparser` does not raise on malformed XML (unlike `rss-parser`), so `parse_error` classification is driven by `feedparser`'s `bozo`/`bozo_exception`/entry-count signal, not by catching a parser exception (FR10, FR11).
- Must pass `ruff check .` under this repo's existing lint config.
- Must pass under `pytest -m "not network"` in CI — tests exercising the fetch path must fake HTTP responses via `pytest-httpserver` (already an installed test dependency) rather than reaching real network endpoints.
- HTTPS-only enforcement (FR2) and the five-code error taxonomy (FR13) are binding CONTRACT.md design rules, not just this doc's preference.
- This repo's secret-scan git hooks (`scripts/install-hooks.sh`) are an assumed-active operational prerequisite in any checkout building this submodule — `steps.md` already references this; it is noted here so requirements.md carries the same assumption.

## Out of scope
- Any storage, database, or on-disk cache of polled items (CONTRACT.md rule 2).
- Deduplication or "have I seen this guid before" logic — the caller's job.
- Scheduling or recurring polling — one call to `poll()` is one fetch.
- Any HTTP scheme other than `https` (no `http://` fallback, no scheme auto-upgrade).
- Any anti-bot evasion, browser automation, stealth headers, or retry-around-blocking logic — a feed gated behind bot detection is explicitly scraper-commons's territory, not this repo's.
- Authenticated/credentialed feeds (API keys, OAuth, cookies) — CONTRACT.md rule 6 defers this to a future, explicitly-designed extension.
- Any submodule other than `poll` (no OPML, no feed-discovery, no webhook/push support) — CONTRACT.md's status section scopes only `poll` as built today.
- Rich/extended feed fields beyond `title`, `link`, `guid`, `pub_date`, `description_excerpt` (e.g. author, categories, enclosures/media) unless a real consumer need is identified later.
- CLI overrides for `excerpt_max_length` or `timeout_seconds` — not supported in v1; the CLI always uses `poll()`'s defaults (300, 15s). This is a deliberate, documented capability gap for non-Python callers who need different values, not an oversight.

## Acceptance criteria
1. Calling `poll("http://example.com/feed.xml", ...)` (non-https) raises/returns an `invalid_url` classification without any network call being made.
2. Calling `poll()` against a URL that is not a well-formed URL at all (per the FR2/FR3 definition — non-`https` scheme, or a `https` URL with no non-empty host/netloc such as `https://` or `https:///path`) returns `invalid_url`.
3. Calling `poll()` against a `pytest-httpserver`-faked endpoint that never responds within `timeout_seconds` returns `timeout`.
4. Calling `poll()` against a faked endpoint returning HTTP 404 or 500 returns `http_error`.
5. Calling `poll()` against a faked endpoint that resets the connection returns `network_error`.
6. Calling `poll()` against a faked endpoint returning a well-formed RSS or Atom body returns a list of normalized items with no error.
7. Calling `poll()` against a feed entry whose description contains HTML tags (e.g. `<p>...</p>`) returns a `description_excerpt` with no `<`/`>` tag characters present, truncated to at most `excerpt_max_length` characters, and the truncation point never falls inside what was an HTML tag in the source.
8. Calling `poll()` against a feed entry with no `guid`/`id` field but a present `link` returns that item's `guid` equal to the `link` value.
9. Calling `poll()` against a feed entry with a valid RFC-822 `pubDate` returns `pub_date` as a valid ISO-8601 string equal to the same instant.
10. Calling `poll()` against a feed entry with a missing or unparseable `pubDate` returns `pub_date` as `null`, never the raw source string.
11. Calling `poll()` against a feed body that is malformed XML with zero parseable entries returns `parse_error`.
12. Calling `poll()` against a feed body that sets `feedparser`'s `bozo` flag via a benign exception (e.g. `NonXMLContentType`) but still yields one or more entries does NOT return `parse_error` — it returns the normalized items.
13. No test in the suite that runs under `pytest -m "not network"` makes a real outbound network call; all fetch-path tests use `pytest-httpserver`.
14. `python -m feed_commons poll <url> --json` against a faked feed with all source entries having a non-empty title and link prints one JSON object to stdout with `"status": "ok"` and exits 0.
15. `python -m feed_commons poll <url> --json` against a faked feed where at least one source entry lacks a non-empty title or a non-empty resolved link (and is therefore skipped rather than included) prints `"status": "degraded"`, with `"items"` containing only the entries that passed the title/link validity check, and exits 0.
16. `python -m feed_commons poll <url> --json` against a faked endpoint that returns HTTP 500 prints `"status": "fail"`, a populated `"error"` field with one of the five bounded codes, an empty `"items"` list, and exits non-zero.
17. No test or manual invocation of `poll()` or the CLI, across any of the above failure paths, surfaces a raw Python exception message, stack trace, or third-party library exception text in the returned/printed error value.
18. `ruff check .` passes with zero violations against all new code added for this submodule.
19. An unanticipated internal exception (not a `requests` or `feedparser` exception) raised during orchestration is still mapped to `network_error` and does not propagate raw to the caller. Separately, a `PollError` already classified by a lower layer (e.g. `timeout` from the fetch layer) propagates out of `poll()` unchanged, not reclassified as `network_error`.
20. Triggering a real `requests` exception (e.g. an actual connection failure against a closed local socket, not a hand-constructed `PollError`) and confirming the resulting classified error contains no fragment of the original exception's message text.
21. A faked endpoint that responds with an HTTP redirect (3xx) to an `http://` URL is classified as `http_error`, and no request is ever made to the redirect target.
