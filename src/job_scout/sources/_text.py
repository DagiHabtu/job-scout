"""Shared text helper for source adapters — dependency-light HTML→text (no bs4)."""

from __future__ import annotations

import re
from html import unescape

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(html: str) -> str:
    """Decode entity-encoded HTML, strip tags, collapse whitespace. Good enough for scoring text."""
    s = unescape(html or "")     # &lt;p&gt; → <p>
    s = _TAG.sub(" ", s)         # drop tags
    s = unescape(s)              # decode any remaining entities (&amp;, &nbsp;, …)
    return _WS.sub(" ", s).strip()
