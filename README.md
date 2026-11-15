# feed-commons

feed-commons is a Python library that fetches one public RSS or Atom feed and returns its items in one fixed shape. Home lab projects share it so each one does not write its own feed poller.

It stores nothing, removes no duplicates, and runs no schedule. Each caller does those jobs itself. `CONTRACT.md` lists the design rules.

## Use it from Python

```python
from feed_commons import poll

items = poll("https://example.com/feed.xml", excerpt_max_length=300, timeout_seconds=15)
for item in items:
    print(item["title"], item["link"], item["pub_date"], item["description_excerpt"])
```

`poll` returns a list of dicts. Each dict has these keys:

| Key | Value |
|---|---|
| `title` | Entry title. |
| `link` | Entry link. |
| `guid` | Entry id. Falls back to `link` if the feed has none. |
| `pub_date` | ISO-8601 date, or `None` if the feed date does not parse. |
| `description_excerpt` | Text with HTML removed, cut to `excerpt_max_length` characters. |

The defaults are 300 characters and a 15 second timeout.

## Use it from the command line

Non-Python programs run the CLI and read JSON from stdout.

```bash
python -m feed_commons poll "https://example.com/feed.xml" --json
```

The output looks like this:

```json
{"status": "ok", "items": [], "error": null}
```

`status` is one of three values:

- `ok`: every entry parsed.
- `degraded`: some entries were skipped. The rest are in `items`.
- `fail`: the poll failed. `error` holds the reason and the exit code is 1.

The CLI always prints JSON. It does not read `--json`. It also cannot change the excerpt length or timeout.

## Errors are short codes

A failed poll raises `PollError`. Its `code` is one of `timeout`, `invalid_url`, `http_error`, `parse_error`, `network_error`. A code never holds the feed URL or the response body, so callers can log it safely.

## Limits

- Only `https://` URLs work. Other schemes give `invalid_url`.
- The fetch does not follow redirects. A redirect gives `http_error`.
- A response over 10 MB gives `http_error`.
- No credentials are sent. Feeds behind a login or bot detection are out of scope. `scraper-commons` and `api-clients-commons` (separate repos) cover those cases.

## Set up for development

1. Clone the repo and run `cd feed-commons`.
2. Run `pip install -e ".[test,dev]"`.
3. Run `pytest -m "not network"`.
4. Run `ruff check .`.
5. Run `scripts/install-hooks.sh` once per clone. It turns on the git hooks and needs `gitleaks`.

## Where things live

- `src/feed_commons/poll.py`: the `poll` function.
- `src/feed_commons/fetch.py`, `parse.py`, `normalize.py`: fetch, parse, and shape the feed.
- `src/feed_commons/cli.py`: the command line entry point.
- `CONTRACT.md`: design rules.
- `docs/poll-submodule/`: the spec for `poll`.
