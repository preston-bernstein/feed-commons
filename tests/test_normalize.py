import time
from types import SimpleNamespace

from feed_commons.errors import PollError
from feed_commons.normalize import (
    extract_description,
    normalize_entry,
    normalize_pub_date,
    resolve_guid,
    strip_html_and_truncate,
)

# 1. HTML stripping + truncation (AC7)


def test_strip_html_and_truncate_direct():
    text = "<p>Hello <b>world</b></p> extra text here"
    result = strip_html_and_truncate(text, 10)
    assert "<" not in result
    assert ">" not in result
    assert len(result) <= 10


def test_normalize_entry_description_excerpt_stripped_and_truncated():
    entry = {
        "title": "Some Title",
        "link": "https://example.com/post",
        "content": [{"value": "<p>Hello <b>world</b></p> extra text here"}],
    }
    item = normalize_entry(entry, excerpt_max_length=10)
    assert item is not None
    excerpt = item["description_excerpt"]
    assert "<" not in excerpt
    assert ">" not in excerpt
    assert len(excerpt) <= 10


# 2. guid fallback to link (AC8)


def test_resolve_guid_falls_back_to_link_when_id_missing():
    assert resolve_guid({}, "https://example.com/a") == "https://example.com/a"


def test_resolve_guid_falls_back_to_link_when_id_empty():
    assert resolve_guid({"id": ""}, "https://example.com/b") == "https://example.com/b"


# 3. guid from entry.id, not entry.guid


def test_resolve_guid_reads_id_field_not_guid_field():
    entry = {"id": "real-guid-123"}
    assert "guid" not in entry
    assert resolve_guid(entry, "https://example.com/ignored") == "real-guid-123"


# 4. both guid and link absent


def test_resolve_guid_empty_when_both_absent():
    assert resolve_guid({}, "") == ""


# 5. pub_date UTC correctness with a non-zero UTC offset source


def test_normalize_pub_date_utc_offset_regression():
    # Represents Wed, 02 Oct 2024 15:00:00 -0700, which in UTC is
    # 2024-10-02T22:00:00+00:00. Constructed directly as UTC field values
    # so a time.mktime (local-time) implementation would produce a
    # different, visibly wrong timestamp.
    utc_struct = time.struct_time((2024, 10, 2, 22, 0, 0, 0, 0, 0))
    entry = {"published_parsed": utc_struct}
    result = normalize_pub_date(entry)
    assert result is not None
    assert result.startswith("2024-10-02T22:00:00")


# 6. pub_date fallback to updated_parsed


def test_normalize_pub_date_falls_back_to_updated_parsed():
    utc_struct = time.struct_time((2024, 1, 1, 12, 0, 0, 0, 0, 0))
    entry = {"published_parsed": None, "updated_parsed": utc_struct}
    result = normalize_pub_date(entry)
    assert result is not None
    assert result.startswith("2024-01-01T12:00:00")


# 7. pub_date null when both absent (AC10)


def test_normalize_pub_date_none_when_both_absent():
    assert normalize_pub_date({}) is None


# 8. missing description (FR20)


def test_extract_description_empty_when_absent():
    entry = {}
    assert extract_description(entry) == ""


# 8b. extract_description: content list, dict-style items ("value" key)


def test_extract_description_from_content_dict_style_returns_value():
    entry = {"content": [{"value": "dict content text"}]}
    assert extract_description(entry) == "dict content text"


def test_extract_description_from_content_dict_style_missing_value_key():
    # dict-style item present but with no "value" key at all -> "" default,
    # never None and never a placeholder default.
    entry = {"content": [{"other": "irrelevant"}]}
    assert extract_description(entry) == ""


# 8c. extract_description: content list, attribute-style items (feedparser
# entries expose .value as an attribute, not a dict key)


def test_extract_description_from_content_attribute_style_returns_value():
    entry = {"content": [SimpleNamespace(value="attr content text")]}
    assert extract_description(entry) == "attr content text"


def test_extract_description_from_content_attribute_style_missing_value_attr():
    entry = {"content": [SimpleNamespace()]}
    assert extract_description(entry) == ""


# 8d. extract_description: empty content list falls through to summary,
# not treated as "content present"


def test_extract_description_empty_content_list_falls_back_to_summary():
    entry = {"content": [], "summary": "fallback summary text"}
    assert extract_description(entry) == "fallback summary text"


# 8e. extract_description: summary fallback (content absent entirely)


def test_extract_description_uses_summary_when_content_absent():
    entry = {"summary": "some summary text"}
    assert extract_description(entry) == "some summary text"


def test_extract_description_empty_summary_does_not_short_circuit():
    # summary present but falsy (empty string) must still fall through to
    # the final "" default, not return the empty summary object itself
    # via a different code path.
    entry = {"summary": ""}
    assert extract_description(entry) == ""


# 9. title/link validity — drop, not flag (AC14/15)


def test_normalize_entry_none_when_title_missing():
    entry = {"link": "https://example.com/x"}
    assert normalize_entry(entry, excerpt_max_length=100) is None


def test_normalize_entry_none_when_title_empty():
    entry = {"title": "  ", "link": "https://example.com/x"}
    assert normalize_entry(entry, excerpt_max_length=100) is None


def test_normalize_entry_none_when_link_missing():
    entry = {"title": "Some Title"}
    assert normalize_entry(entry, excerpt_max_length=100) is None


def test_normalize_entry_none_when_link_empty():
    entry = {"title": "Some Title", "link": "  "}
    assert normalize_entry(entry, excerpt_max_length=100) is None


def test_normalize_entry_valid_returns_item():
    entry = {"title": "Some Title", "link": "https://example.com/x"}
    item = normalize_entry(entry, excerpt_max_length=100)
    assert item is not None
    assert item["title"] == "Some Title"
    assert item["link"] == "https://example.com/x"


# 10. normalize_entry actually computes and includes pub_date (not None,
# not omitted from the returned dict)


def test_normalize_entry_includes_computed_pub_date():
    utc_struct = time.struct_time((2024, 3, 5, 8, 30, 0, 0, 0, 0))
    entry = {
        "title": "Some Title",
        "link": "https://example.com/x",
        "published_parsed": utc_struct,
    }
    item = normalize_entry(entry, excerpt_max_length=100)
    assert item is not None
    assert item["pub_date"] == "2024-03-05T08:30:00+00:00"


# 11. _TextExtractor.get_text joins chunks with no separator (multiple
# handle_data() calls must not gain any inserted characters between them)


def test_strip_html_and_truncate_joins_chunks_without_separator():
    text = "<p>Hello <b>world</b></p> extra text here"
    result = strip_html_and_truncate(text, 100)
    assert result == "Hello world extra text here"


# 12. PollError preserves the original error code as the exception's args,
# not a mangled/None value


def test_poll_error_preserves_code_in_args_and_message():
    err = PollError("timeout")
    assert err.code == "timeout"
    assert err.args == ("timeout",)
    assert str(err) == "timeout"
