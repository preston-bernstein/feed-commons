# feed-commons

This is a scaffold, not a finished library. feed-commons is meant to be
**imported** (Python) or **shelled out to via its CLI** (non-Python
consumers, e.g. a TypeScript app) by home-lab projects — not run as a
standalone service. Each submodule gets implemented only when the first real
project needs it, extracted from that real use, never written ahead of time
on spec. See `CONTRACT.md` for the intended shape.

This is a third, sibling application of the same shared-library split
`scraper-commons` and `api-clients-commons` already establish:
`home-infra/docs/adr/0015-shared-scraper-library.md` (the general
imported-library-gets-a-dedicated-repo decision) and
`home-infra/docs/adr/0023-dedicated-lib-repos-for-fleet-logging-and-ollama-client.md`
(a second concrete application of that same split). No new ADR was written
for this repo, matching `api-clients-commons`' own precedent — it cites
0015/0023 rather than getting a unique entry, since this isn't a new
architectural decision, just another instance of the established one.

Distinct from both siblings: `scraper-commons` holds stealth/anti-detection
scraping logic for sites with no official API or feed; `api-clients-commons`
holds real, credentialed API clients for sites that offer an authenticated
API. This repo holds public, unauthenticated feed polling (RSS/Atom/etc.) —
no browser automation, no stealth, no bot-detection evasion. A feed source
that's gated behind bot detection (no working public feed) is out of scope
here, same as it's out of scope for `api-clients-commons` — that's
`scraper-commons` territory, a different, deliberate choice the caller
makes, never auto-detected.

Cross-cutting home-lab conventions (service users, secrets, the shared
library vs. shared service split) live in `home-infra/CONVENTIONS.md`.

## Remotes

A single `git push` to `origin` writes to two remotes: the NAS (primary,
`ssh://nas-agent/.../feed-commons.git`) first, then GitHub (offsite mirror,
`preston-bernstein/feed-commons`, private) second. `git fetch` only reads
from the NAS.

## Secret-scan gate — run once per clone

Git hooks that scan for secrets live in `.githooks/` and are checked into
the repo, but git does not turn them on automatically. On any fresh clone,
run **`scripts/install-hooks.sh`** once. It points git at that hooks folder
(`core.hooksPath`) and checks that `gitleaks` is installed.

Once enabled, the pre-commit hook blocks any commit that stages a secret or
a real `.env` file, and the pre-push hook scans outgoing commits before they
can reach the GitHub mirror. This fails closed: if the `gitleaks` binary
isn't installed, commits and pushes are refused rather than let through
unscanned. Install it with `brew install gitleaks`. The scan rules and
allowlist live in `.gitleaks.toml`.
