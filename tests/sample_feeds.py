"""Feed bodies and a scheme-check bypass shared by the CLI and poll tests."""

from unittest.mock import patch


def bypass_scheme_check():
    """No-op the HTTPS-only check inside fetch.py for tests that need to hit
    a real (plain-HTTP) local test server. The scheme check has its own tests in test_fetch.py.
    """
    return patch("feed_commons.fetch.validate_https_url", lambda url: None)


RSS_TWO_VALID_ITEMS = b"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item>
<title>Item 1</title>
<link>https://example.com/1</link>
<description>First item body</description>
</item>
<item>
<title>Item 2</title>
<link>https://example.com/2</link>
<description>Second item body</description>
</item>
</channel>
</rss>
"""

RSS_MIXED_VALID_INVALID = b"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Mixed Feed</title>
<item>
<title>Valid Item 1</title>
<link>https://example.com/valid1</link>
</item>
<item>
<title></title>
<link>https://example.com/no-title</link>
</item>
<item>
<title>No Link Item</title>
<link></link>
</item>
<item>
<title>Valid Item 2</title>
<link>https://example.com/valid2</link>
</item>
</channel>
</rss>
"""
