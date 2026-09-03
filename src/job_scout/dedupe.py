"""Within-run deduplication — an entity-resolution problem.

Tiered: (1) exact ATS identity, (2) content fingerprint, (3) fuzzy title match BLOCKED by company
(a duplicate is essentially never across two employers, so blocking keeps this near-linear instead
of O(n^2)). Bias is toward false-splits over false-merges: the threshold is conservative and all
source provenance is retained, so a wrong merge stays visible and recoverable.

NOTE: uses stdlib difflib for fuzzy matching to stay dependency-light in Phase 0. The production
choice is rapidfuzz (C-backed token_set_ratio) — a drop-in swap flagged in STATE for Phase 2.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from difflib import SequenceMatcher

from .models import Opportunity, content_fingerprint

_FUZZY_THRESHOLD = 0.90  # conservative: only near-identical titles within one company merge


def _canon_company(c: str) -> str:
    return content_fingerprint(c, "", None)  # reuse the canonicaliser for a stable company key


def _merge(into: Opportunity, other: Opportunity) -> Opportunity:
    """Merge `other` into `into` — the STABLE canonical (first-seen) object that stays in the output.

    Provenance is always unioned so no source is lost. When `other` carries the richer record
    (strictly longer description), its content is promoted ONTO `into`, so the richer duplicate
    wins while the object identity in the output list stays the first-seen one. First-seen wins ties.

    The previous version returned `other` when it was richer, but callers kept the first-seen object
    in the output list — so a richer *second* occurrence (and its unioned provenance) was dropped.
    Mutating the canonical `into` in place fixes that: the object every tier holds is the one that
    accumulates.
    """
    # Union provenance into the canonical object: `into`'s entries first, then `other`'s new ones.
    seen = {(p.source, p.url) for p in into.provenance}
    merged_provenance = list(into.provenance)
    for p in other.provenance:
        if (p.source, p.url) not in seen:
            merged_provenance.append(p)
            seen.add((p.source, p.url))

    # Promote the richer record's content wholesale (matches the original "keep the richer record"
    # intent), but onto the stable `into` object rather than by swapping which object survives.
    if len(other.description) > len(into.description):
        for f in dataclass_fields(into):
            setattr(into, f.name, getattr(other, f.name))

    into.provenance = merged_provenance
    return into


def dedupe(opps: list[Opportunity]) -> list[Opportunity]:
    by_identity: dict[tuple[str, str], Opportunity] = {}
    survivors: list[Opportunity] = []

    for opp in opps:
        # Tier 1 — exact ATS identity.
        if opp.ats_provider and opp.ats_job_id:
            key = (opp.ats_provider, opp.ats_job_id)
            if key in by_identity:
                _merge(by_identity[key], opp)  # mutates the first-seen object already in survivors
                continue
            by_identity[key] = opp
            survivors.append(opp)
            continue
        survivors.append(opp)

    # Tier 2 — content fingerprint.
    by_fp: dict[str, Opportunity] = {}
    tier2: list[Opportunity] = []
    for opp in survivors:
        fp = opp.content_fingerprint or content_fingerprint(opp.company, opp.title, opp.location_raw)
        if fp in by_fp:
            _merge(by_fp[fp], opp)  # mutates the first-seen object already in tier2
            continue
        by_fp[fp] = opp
        tier2.append(opp)

    # Tier 3 — fuzzy title, blocked by company.
    final: list[Opportunity] = []
    per_company: dict[str, list[Opportunity]] = {}
    for opp in tier2:
        ckey = _canon_company(opp.company)
        bucket = per_company.setdefault(ckey, [])
        dup_of = None
        for existing in bucket:
            if SequenceMatcher(None, existing.title.lower(), opp.title.lower()).ratio() >= _FUZZY_THRESHOLD:
                dup_of = existing
                break
        if dup_of is not None:
            _merge(dup_of, opp)  # mutates the first-seen object already in final
        else:
            bucket.append(opp)
            final.append(opp)

    return final
