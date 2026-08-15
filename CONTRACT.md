# Contract: feed-commons

## Intended shape

A stateless RSS/Atom feed-polling library: given a feed URL, fetch it,
parse it, and return a normalized list of items. No storage, no
deduplication, no scheduling — those stay the caller's job, since every
consumer so far has its own storage shape (internal-monitor-app uses SQLite with
its own dedupe-on-`(source_id, guid)` schema; a future consumer might use
something else entirely). feed-commons's job stops at "here are today's
items, normalized the same way every time."

This is the same YAGNI discipline `scraper-commons` and `api-clients-commons`
already use for their own modules — one real submodule (`poll`) exists
because one real project needs it today (internal-monitor-app's New Balance
press-release feed). Nothing else gets speculatively pre-built.

## Design rules

1. **Explicit URL, not auto-detected.** The primary entry point takes an
   already-known feed URL as an explicit argument — never a raw hostname
   that gets silently sniffed or routed. There is no logic anywhere in this
   repo that guesses whether a given URL is a feed.
2. **Stateless.** No database, no on-disk cache, no "have I seen this guid
   before" logic. `poll(url)` returns everything the feed currently serves,
   normalized; the caller decides what's new.
3. **HTTPS-only, no anti-bot evasion.** A non-`https` URL is rejected before
   any fetch is attempted. A feed that 403s behind bot detection (Cloudflare,
   PerimeterX, etc.) is out of scope — that's what a real, working public
   feed exists to avoid needing in the first place. This repo never grows
   stealth/browser-automation logic; that's `scraper-commons`'s job, and the
   two repos never import from each other.
4. **Structured, bounded errors — never a raw exception message surfaces to
   a caller's logs/storage layer.** A failure classifies into one of a fixed
   set of reason codes (`timeout`, `invalid_url`, `http_error`,
   `parse_error`, `network_error`) rather than a free-text exception string,
   so a caller's health/logging layer never accidentally retains a raw feed
   URL or response body.
5. **A CLI entry point exists for every submodule**, so a non-Python
   consumer (e.g. a TypeScript app) can shell out and get JSON on stdout,
   without needing a Python import boundary. The Python API is still the
   primary interface for Python callers — the CLI is the cross-language
   escape hatch, not the other way around.
6. **No credentials in v1.** Every submodule so far polls public,
   unauthenticated feeds. If a real consumer needs an authenticated feed
   later, that's a new, explicit extension to design then — not a default
   this repo assumes.

## Status today

- **`poll`** — implemented. Fetches one feed URL over HTTPS (via
  `feedparser`, which handles RSS 0.9x/1.0/2.0/CDF/Atom 0.3/1.0), returns a
  list of normalized items: `title`, `link`, `guid` (falls back to `link`
  when the feed omits one), `pub_date` (parsed to ISO-8601, or `null` if the
  feed's date doesn't parse), and `description_excerpt` (HTML-stripped,
  truncated to a caller-supplied max length — default 300 characters).
  Extracted from internal-monitor-app's `apps/cli/src/pipeline/bulletin-poll.ts`
  (its first real, already-shipped consumer) — the normalization rules
  above (HTML-strip-before-truncate, guid-falls-back-to-link,
  parse-or-null pubDate, bounded error codes) match that implementation
  exactly, generalized to any feed rather than one hardcoded source.
