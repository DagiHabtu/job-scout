"""Cross-cutting normalization — the pipeline's job, never a source's.

Canonicalizes each Opportunity so downstream identity/dedupe/scoring are stable: strips tracking
params to a canonical URL, infers remote status from text when a source left it UNKNOWN (honestly
staying UNKNOWN when there is no signal), and computes the content fingerprint.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import EmploymentType, Opportunity, RemoteStatus, content_fingerprint

# Query params that are tracking noise, not identity. Everything else is preserved (ATS apply URLs
# often carry a meaningful job token in the query, so we strip conservatively).
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source", "src", "gh_src"}


def strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


# An explicit internship token in a TITLE. Anchored on word boundaries so "internal" and
# "international" never match; covers intern/interns/internship(s) and co-op/coop/co-ops.
_INTERN_TITLE = re.compile(r"\b(intern(ship)?s?|co-?ops?)\b", re.IGNORECASE)


def infer_employment_type(opp: Opportunity) -> EmploymentType:
    """Backfill INTERNSHIP from an explicit title token when the source left the type UNKNOWN.

    Symmetric to `infer_remote_status`: a source with a structured employment field (Lever's
    `commitment`, Ashby's `employmentType`) already sets this and is left untouched; a source
    without one (Greenhouse's board API exposes no employment-type field, so its adapter honestly
    emits UNKNOWN) would otherwise leave an unmistakable "Software Engineering Intern" unrecognized
    as an internship for the whole pipeline — no wanted-type boost, a harder notification bar, and
    indistinguishable at the type level from every other UNKNOWN role.

    Deliberately narrow: TITLE-only (a description mentioning "our interns" must not reclassify a
    full-time role) and INTERNSHIP-only (the one type inferable from a title with high precision).
    It only ever fills an UNKNOWN — it never overrides a source's structured value, and it stays
    UNKNOWN when the title carries no signal.
    """
    if opp.employment_type != EmploymentType.UNKNOWN:
        return opp.employment_type
    if _INTERN_TITLE.search(opp.title or ""):
        return EmploymentType.INTERNSHIP
    return EmploymentType.UNKNOWN


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
    opp.employment_type = infer_employment_type(opp)
    opp.content_fingerprint = content_fingerprint(opp.company, opp.title, opp.location_raw)
    if opp.discovered_date is None:
        opp.discovered_date = datetime.now(timezone.utc)
    return opp
