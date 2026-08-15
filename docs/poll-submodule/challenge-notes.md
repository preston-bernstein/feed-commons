# Spec Challenge Notes

## Agents run
- Requirements Auditor (haiku): 7 issues found, 4 accepted
- Scope & Dependency Auditor (sonnet): 7 issues found, 6 accepted
- Design Devil's Advocate (sonnet): 11 issues found, 9 accepted
- Implementation Realist (sonnet): 6 findings found, 6 accepted
- Steps & Sequencing Critic (sonnet): 12 issues found, 6 accepted
- Data Model Critic (sonnet): 9 issues found, 4 accepted
- Security/Threat Auditor (haiku): 1 issue found, 1 accepted (as documented risk, not a build requirement)

## Changes made

- **Item validity rule changed from "keep and flag" to "drop invalid items."** The original spec kept an item with a missing title in `items` with an issue flag. Three independent agents (Scope Auditor, Implementation Realist, and cross-checked against fashion-monitor's actual shipped `bulletin-poll.ts`) caught that this contradicts the reference implementation's `isValidItem`, which requires a non-empty title AND link and drops the whole item otherwise. Rewritten to match the reference: an entry with an empty title or link is skipped entirely, and `"status": "degraded"` now means "at least one entry was skipped," not "a kept item has an issue." This also simplified the plan — removed the `ItemIssues` dual-flag type.
- **HTTPS-redirect-downgrade gap closed.** Two independent agents (Data Model Critic, Design Devil's Advocate) caught that `requests` follows redirects by default, so an `https://` feed could 301 to `http://` and silently defeat FR2's HTTPS-only enforcement. Fixed by disabling `allow_redirects` and routing any 3xx response through the existing non-2xx → `http_error` path — no new error code needed.
- **`poll.py`'s catch-all exception handler would have swallowed already-classified errors.** The Implementation Realist agent caught that a naive `except Exception` catches `PollError` too (it's an `Exception` subclass), which would silently reclassify every specific code (`timeout`, `http_error`, etc.) down to generic `network_error` — defeating the whole taxonomy. Fixed by requiring an explicit `except PollError: raise` before the catch-all, plus a debug-log of the real exception so ops don't lose the signal.
- **Wrong feedparser field names would have produced silently-broken normalization.** The Implementation Realist agent caught that the plan named `entry.guid` (rarely populated by feedparser) instead of `entry.id` (feedparser's actual normalized field for both RSS guid and Atom id), and left the description-field precedence (`content` vs `summary` vs `description`) completely unspecified. Both are now pinned down explicitly.
- **UTC timezone bug flagged as a required test, not just prose.** The pub_date conversion risk (`time.mktime` silently shifts every timestamp by the local UTC offset, and GitHub Actions' UTC runners wouldn't catch it) was already in the original plan's Risk section as prose. Promoted it to a concrete required test assertion (a source date with a non-zero UTC offset) so a regression actually fails CI instead of only being "documented."
- **Step 8's own verification command couldn't have passed.** The Steps & Sequencing Critic and Implementation Realist both independently caught that Step 8 tested `from feed_commons import poll`, but `__init__.py` isn't wired to export `poll` until Step 13 — the test would `ImportError` at the exact point it was meant to run. Fixed to import from the submodule directly.

## Critiques rejected
- Full SSRF protection (Security Auditor) — accepted as a documented, explicit risk note in requirements.md rather than a v1 build requirement. This library serves a home-lab trusted-caller context (the only real consumer today polls one fixed brand feed URL, not attacker-controlled input); full network-destination filtering is speculative scope for now, consistent with this repo's stated no-gold-plating discipline.
- CLI flags for `excerpt_max_length`/`timeout_seconds` (Design Devil's Advocate) — not built; documented as a deliberate, known gap in Out of scope instead. No FR asked for it, and adding it now would be speculative.
- `_PollOutcome` as a tuple instead of a dataclass (Design Devil's Advocate) — too minor to act on; the named-field dataclass is fine for a two-field internal carrier.
- Splitting Step 2 (`normalize.py`) into two smaller steps (Steps & Sequencing Critic) — left as one step; the five functions are cohesive and the step still fits the 2-hour bound.
- "Unverifiable" flags on Steps 2/4/6/10 (Steps & Sequencing Critic) — rejected as a false pattern match. Each of those steps is deliberately followed by its own dedicated test step (3/5/7/11) that exercises the real logic; the module step's own smoke test is intentionally minimal.

## Open questions requiring human input
None. All findings were either resolved directly in the spec rewrite or explicitly scoped out with a documented reason above.
