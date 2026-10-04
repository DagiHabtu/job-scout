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


# Title level tokens (spec S3, exact). Word-boundaried so "internal"/"international" never match.
_INTERN_TITLE = re.compile(
    r"\b(intern(ship)?s?|co-?ops?|working student|werkstudent(in)?|trainee|apprentice(ship)?)\b", re.IGNORECASE
)
_ENTRY_TITLE = re.compile(
    r"\b(junior|jr\.?|entry[- ]level|new[- ]grad(uate)?|graduate|early[- ]career|associate (software|data|ml|"
    r"machine learning|devops|platform|cloud|security|qa|site reliability) (engineer|developer|analyst|scientist))\b",
    re.IGNORECASE,
)
_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|head|director|manager|vp|chief|architect)\b", re.IGNORECASE
)


def infer_employment_type(opp: Opportunity) -> EmploymentType:
    """Infer the employment type/level from TITLE tokens where the source is silent or coarse.

    * UNKNOWN + an intern token → INTERNSHIP. (Greenhouse exposes no employment-type field, so its
      adapter honestly emits UNKNOWN; an unmistakable "Software Engineering Intern" must still be
      recognized.)
    * UNKNOWN or FULL_TIME + an entry-level token and no seniority token → NEW_GRAD. Refining
      FULL_TIME is consistent with the enum ("entry-level / early-career full-time"): a structured
      "Full Time" says nothing about level, the title does.

    Any other structured value (INTERNSHIP, CONTRACT, STIPEND_PROGRAM, NEW_GRAD) is left untouched.
    TITLE-only: a description mentioning "our interns" must not reclassify a full-time role.
    """
    title = opp.title or ""
    if opp.employment_type == EmploymentType.UNKNOWN and _INTERN_TITLE.search(title):
        return EmploymentType.INTERNSHIP
    if (
        opp.employment_type in (EmploymentType.UNKNOWN, EmploymentType.FULL_TIME)
        and _ENTRY_TITLE.search(title)
        and not _SENIOR_TITLE.search(title)
    ):
        return EmploymentType.NEW_GRAD
    return opp.employment_type


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
