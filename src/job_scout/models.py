"""Canonical domain models — THE FROZEN SPINE.

Every source normalizes into `Opportunity`; every pipeline stage reads it. Changing anything in
this file after Gate 0 requires the spine-architect and a `Decisions that override PLAN` entry in
STATE.md. See PLAN.md §Spine.

Deliberately dependency-light (stdlib dataclasses + enums): the canonical record has no reason to
pull in a validation framework, and keeping it plain makes it trivially importable by every agent.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

# --------------------------------------------------------------------------------------------- #
# Enums — every one carries UNKNOWN as a first-class value. "Unknown" is never faked as a default
# that happens to look like a real answer (e.g. never silently treat unspecified as ONSITE).
# --------------------------------------------------------------------------------------------- #


class EmploymentType(str, Enum):
    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"          # entry-level / early-career full-time
    FULL_TIME = "full_time"
    CONTRACT = "contract"
    STIPEND_PROGRAM = "stipend_program"   # Outreachy / GSoC-class: a program, not employment
    UNKNOWN = "unknown"


class RemoteStatus(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EligibilityCategory(str, Enum):
    """How reachable this opportunity is for the user at their configured location.

    Ordered loosely best→worst for intuition; ranking uses explicit weights, not this order.
    """

    STIPEND_PROGRAM_GLOBAL = "stipend_program_global"        # structurally open worldwide
    WORLDWIDE_REMOTE = "worldwide_remote"                    # "remote, anywhere"
    REMOTE_REGION_INCLUDES_USER = "remote_region_includes_user"   # e.g. EMEA/Africa incl. ET
    UNKNOWN = "unknown"                                      # cannot tell — SURFACE, don't drop
    REQUIRES_WORK_AUTH = "requires_work_auth"               # needs auth the user lacks (disqualifying)
    REMOTE_EXCLUDES_USER = "remote_excludes_user"           # e.g. "Remote (US only)" (disqualifying)
    ONSITE_FOREIGN = "onsite_foreign"                       # onsite in a country the user isn't in


# Categories that disqualify an opportunity when asserted with high confidence.
DISQUALIFYING_ELIGIBILITY = frozenset(
    {
        EligibilityCategory.REQUIRES_WORK_AUTH,
        EligibilityCategory.REMOTE_EXCLUDES_USER,
        EligibilityCategory.ONSITE_FOREIGN,
    }
)


class Lifecycle(str, Enum):
    NEW = "new"          # first seen this run
    ACTIVE = "active"    # seen again, unchanged
    UPDATED = "updated"  # content changed since last run
    EXPIRED = "expired"  # deadline passed
    GONE = "gone"        # absent from a SUCCESSFULLY-fetched source for K consecutive runs


# --------------------------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------------------------- #


@dataclass
class Eligibility:
    """A judgement about reachability, held honestly.

    `confidence` in [0, 1]. A disqualifying category counts as a hard fail only when confidence is
    high (threshold lives in the scorer/config, not here). `evidence` records the concrete signals
    that drove the call so the digest — and a human — can audit it.
    """

    category: EligibilityCategory
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def is_confident_disqualifier(self, threshold: float) -> bool:
        return self.category in DISQUALIFYING_ELIGIBILITY and self.confidence >= threshold


@dataclass
class Relevance:
    """A composite relevance judgement with legible components — never a bare number.

    `semantic_similarity` is the local-embedding cosine (0..1) or None before scoring.
    `score` is the combined rank input. `matched_signals` / `concerns` make it explainable.
    """

    score: float
    matched_signals: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    semantic_similarity: float | None = None


@dataclass
class Provenance:
    """Where this opportunity was seen. A list per Opportunity: the same role legitimately arrives
    from multiple sources with different URLs, and we keep every one so a bad merge is recoverable.
    """

    source: str
    url: str
    first_seen: datetime


# --------------------------------------------------------------------------------------------- #
# The canonical record
# --------------------------------------------------------------------------------------------- #


@dataclass
class Opportunity:
    # --- identity (drives deduplication) ---
    title: str
    company: str
    apply_url: str
    canonical_url: str                       # apply_url with tracking params stripped
    ats_provider: str | None = None          # "greenhouse" | "lever" | ... | None
    ats_job_id: str | None = None            # stable per-provider id when available
    content_fingerprint: str = ""            # hash(normalized company+title+location); see helper

    # --- core (honest nulls) ---
    location_raw: str | None = None
    remote_status: RemoteStatus = RemoteStatus.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    description: str = ""
    technologies: list[str] = field(default_factory=list)
    posting_date: date | None = None
    deadline: date | None = None
    salary_raw: str | None = None
    salary_is_estimated: bool = False        # True when pay came from an aggregator's prediction

    # --- derived / enriched (filled by the pipeline, never by a source) ---
    eligibility: Eligibility | None = None
    relevance: Relevance | None = None

    # --- lifecycle / provenance ---
    status: Lifecycle = Lifecycle.NEW
    provenance: list[Provenance] = field(default_factory=list)
    discovered_date: datetime | None = None
    notified_at: datetime | None = None
    history: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------- #
# Identity helpers (shared normalization — a source does not compute these; the pipeline does)
# --------------------------------------------------------------------------------------------- #

_WS = re.compile(r"\s+")
_NONALNUM = re.compile(r"[^a-z0-9 ]+")


def _canon_text(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for stable fingerprints/matching."""
    s = _NONALNUM.sub(" ", s.lower())
    return _WS.sub(" ", s).strip()


def content_fingerprint(company: str, title: str, location: str | None) -> str:
    """Identity for content-level dedupe: same role from different sources → same fingerprint.

    Uses company+title+location only (not description or URL), because those are the fields that
    stay stable across sources while descriptions get reworded and URLs differ.
    """
    basis = "|".join((_canon_text(company), _canon_text(title), _canon_text(location or "")))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
