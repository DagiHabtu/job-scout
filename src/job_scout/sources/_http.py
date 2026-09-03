"""Shared HTTP helper for source adapters — stdlib only ($0, no `requests`).

`get_json` GETs a URL and returns parsed JSON, or RAISES. A non-JSON body raises (rather than
returning nothing) because "the endpoint served HTML instead of JSON" is a total failure — notably
Lever, which intermittently returns an HTML page even with `mode=json`. Per the `Source` contract a
total failure must propagate (the pipeline isolates it), never be swallowed into an empty list.
"""

from __future__ import annotations

import json
import urllib.request

USER_AGENT = "job-scout/0.1 (+https://github.com/; zero-cost eligibility-first job scout)"


def get_json(url: str, *, timeout: float = 20.0, headers: dict | None = None):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # raises HTTPError/URLError
        body = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        snippet = body[:80].decode("utf-8", "replace")
        raise RuntimeError(f"non-JSON response from {url} (content-type {ctype!r}): {snippet!r}") from exc
