import calendar
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import TypedDict


class NormalizedItem(TypedDict):
    title: str
    link: str
    guid: str
    pub_date: str | None
    description_excerpt: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def resolve_guid(entry: dict, link: str) -> str:
    raw_id = entry.get("id")
    if raw_id is not None:
        stripped = str(raw_id).strip()
        if stripped:
            return stripped
    if link:
        return link
    return ""


def extract_description(entry: dict) -> str:
    content = entry.get("content")
    if content:
        first = content[0]
        if hasattr(first, "get"):
            return first.get("value", "")
        return getattr(first, "value", "")
    summary = entry.get("summary")
    if summary:
        return summary
    return ""


def strip_html_and_truncate(text: str, max_length: int) -> str:
    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    stripped = parser.get_text()
    return stripped[:max_length]


def normalize_pub_date(entry: dict) -> str | None:
    struct_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct_time is None:
        return None
    ts = calendar.timegm(struct_time)
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def normalize_entry(entry: dict, excerpt_max_length: int) -> NormalizedItem | None:
    title = entry.get("title", "").strip()
    link = entry.get("link", "").strip()

    if not title or not link:
        return None

    return NormalizedItem(
        title=title,
        link=link,
        guid=resolve_guid(entry, link),
        pub_date=normalize_pub_date(entry),
        description_excerpt=strip_html_and_truncate(extract_description(entry), excerpt_max_length),
    )
