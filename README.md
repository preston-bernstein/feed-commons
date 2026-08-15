# feed-commons

feed-commons is a shared Python library for the home lab's projects
(fashion-monitor, and future ones) that need to poll a public RSS or Atom
feed — fetch it, parse it, and get back a normalized list of items. No
storage, no dedupe, no scheduling: those stay each caller's own job, since
every consumer so far has a different storage shape.

## How this differs from its siblings

`scraper-commons` (a separate repo) holds stealth and anti-detection logic —
a Playwright-based browser that mimics a real human, used against sites with
no official API or feed. `api-clients-commons` (also separate) holds real,
credentialed API clients for sites that offer an authenticated API. This
repo is neither: it polls public, unauthenticated feeds only. A feed source
gated behind bot detection is out of scope here — see `CONTRACT.md`.

## Built when a real consumer needs it, not speculatively

`CONTRACT.md` defines the intended shape — a stateless `poll(url)`
primitive plus a CLI entry point for non-Python consumers — but each
submodule is only built once a real project needs it, same discipline
`scraper-commons` and `api-clients-commons` use for their own modules.
Status today:

- **`poll`** — implemented. Fetches and normalizes one feed URL. Extracted
  from fashion-monitor's New Balance press-release feed poller, its first
  real consumer.

## Using the poll function

```python
from feed_commons import poll

result = poll("https://example.com/feed.xml", excerpt_max_length=300, timeout_seconds=15)
for item in result.items:
    print(item.title, item.link, item.pub_date, item.description_excerpt)
```

## Using the CLI (non-Python consumers)

```bash
python -m feed_commons poll "https://example.com/feed.xml" --json
```

Prints a JSON object on stdout: `{"status": "ok"|"degraded"|"fail", "items": [...], "error": "..."}`.
