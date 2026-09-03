"""Cross-cutting normalization — the pipeline's job, never a source's.

Canonicalizes each Opportunity so downstream identity/dedupe/scoring are stable: strips tracking
params to a canonical URL, infers remote status from text when a source left it UNKNOWN (honestly
staying UNKNOWN when there is no signal), and computes the content fingerprint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Opportunity, RemoteStatus, content_fingerprint

# Query params that are tracking noise, not identity. Everything else is preserved (ATS apply URLs
# often carry a meaningful job token in the query, so we strip conservatively).
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source", "src", "gh_src"}


def strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def infer_remote_status(opp: Opportunity) -> RemoteStatus:
    if opp.remote_status != RemoteStatus.UNKNOWN:
        return opp.remote_status
    hay = f"{opp.title} {opp.description} {opp.location_raw or ''}".lower()
    if any(w in hay for w in ("hybrid",)):
        return RemoteStatus.HYBRID
    if any(w in hay for w in ("remote", "work from home", "work from anywhere", "distributed team")):
        return RemoteStatus.REMOTE
    if any(w in hay for w in ("on-site", "on site", "in-office", "in office", "onsite")):
        return RemoteStatus.ONSITE
    return RemoteStatus.UNKNOWN  # no signal — stay honest


def normalize(opp: Opportunity) -> Opportunity:
    opp.canonical_url = strip_tracking(opp.apply_url or opp.canonical_url or "")
    opp.remote_status = infer_remote_status(opp)
    opp.content_fingerprint = content_fingerprint(opp.company, opp.title, opp.location_raw)
    if opp.discovered_date is None:
        opp.discovered_date = datetime.now(timezone.utc)
    return opp
