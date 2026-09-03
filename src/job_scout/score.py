"""Relevance scoring, hard-constraint filtering, and ranking — all $0.

Relevance is a legible composite, never a bare number. Its base is the local-embedding cosine when
the model is available; when it is not (e.g. this sandbox, or a first run before download), it
degrades GRACEFULLY to lexical overlap so the system still works at $0. Eligibility GATES rank: a
confident can't-hire-you opportunity is filtered out entirely, and among survivors a known-eligible
one outranks an equally-relevant unknown-eligibility one.
"""

from __future__ import annotations

import re
from datetime import date

from .config import ScoringConfig, UserProfile
from .models import (
    Eligibility,
    EligibilityCategory,
    EmploymentType,
    Opportunity,
    Relevance,
)

# Eligibility categories that survive hard-filtering, ranked (higher = better) so ranking can honour
# "eligible-known outranks unknown." Disqualifiers never reach ranking (they are filtered out).
_ELIGIBILITY_RANK = {
    EligibilityCategory.STIPEND_PROGRAM_GLOBAL: 3,
    EligibilityCategory.WORLDWIDE_REMOTE: 3,
    EligibilityCategory.REMOTE_REGION_INCLUDES_USER: 2,
    EligibilityCategory.UNKNOWN: 1,
}


# --------------------------------------------------------------------------------------------- #
# Optional local embedding model (lazy, cached, failure-tolerant)
# --------------------------------------------------------------------------------------------- #

_model_cache: dict[str, object] = {}


def load_model(model_id: str):
    """Try to load the local sentence-transformer. Returns the model, or None if unavailable.

    None is a normal, expected outcome (no network for the one-time download, or the package not
    installed) — the scorer falls back to lexical. This is what makes the ML component optional.
    """
    if model_id in _model_cache:
        return _model_cache[model_id]
    try:  # pragma: no cover - exercised only where the model can actually load
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_id)
    except Exception:
        model = None
    _model_cache[model_id] = model
    return model


def _profile_text(p: UserProfile) -> str:
    return " ".join([*p.target_roles, *p.target_technologies, *p.preferred_industries, p.experience_level])


def embed_similarity(opp: Opportunity, profile: UserProfile, model) -> float | None:
    if model is None:
        return None
    try:  # pragma: no cover - only where a real model is present
        import numpy as np

        vecs = model.encode([_profile_text(profile), f"{opp.title}. {opp.description}"], normalize_embeddings=True)
        return float(np.dot(vecs[0], vecs[1]))
    except Exception:
        return None


# --------------------------------------------------------------------------------------------- #
# Lexical signals — cheap, deterministic, and the source of legible match reasons
# --------------------------------------------------------------------------------------------- #


_MODEL_UNAVAILABLE = "semantic model unavailable — lexical relevance only"


def _wb(term: str, text: str) -> bool:
    """Word-boundary containment — 'go' matches 'go' but not 'category'; 'lead' not 'leadership'.

    Bare substring matching (the original) produced false hits: short tech tokens matched inside
    unrelated words, and penalize keywords matched prose ('you will lead ...'), firing on nearly
    every posting. Multi-word terms ('open source') are matched as the whole phrase.
    """
    term = term.strip().lower()
    return bool(term) and re.search(rf"\b{re.escape(term)}\b", text) is not None


def lexical_signals(opp: Opportunity, profile: UserProfile) -> tuple[list[str], list[str], float]:
    title = opp.title.lower()
    hay = f"{opp.title} {opp.description} {' '.join(opp.technologies)}".lower()
    matched: list[str] = []
    concerns: list[str] = []

    # Positive signals are FEATURES that can legitimately appear anywhere (a tech named deep in the
    # description is a real match) → scan the whole text, word-boundaried.
    tech_hits = [t for t in profile.target_technologies if _wb(t, hay)]
    role_hits = [r for r in profile.target_roles if all(_wb(w, hay) for w in r.lower().split())]
    kw_hits = [k for k in profile.keywords_prioritize if _wb(k, hay)]
    matched += [f"tech: {t}" for t in tech_hits]
    matched += [f"role match: {r}" for r in role_hits]
    matched += [f"keyword: {k}" for k in kw_hits]

    # A penalize keyword names a KIND of role to avoid (senior/staff/manager/clearance) — that is a
    # TITLE property. Matching it in body prose fires on almost everything and stops discriminating,
    # so seniority/exclusion penalties read the title only.
    penalties = [k for k in profile.keywords_penalize if _wb(k, title)]
    concerns += [f"penalized keyword: {k}" for k in penalties]

    # Normalize to 0..1: reward overlap breadth, dampened; subtract penalties.
    want = max(1, len(profile.target_technologies) + len(profile.target_roles))
    raw = (len(tech_hits) + 2 * len(role_hits) + len(kw_hits)) / (want + 1)
    score = max(0.0, min(1.0, raw) - 0.15 * len(penalties))
    return matched, concerns, score


def score_opportunity(opp: Opportunity, profile: UserProfile, cfg: ScoringConfig, model=None) -> Relevance:
    matched, concerns, lexical = lexical_signals(opp, profile)
    sim = embed_similarity(opp, profile, model)
    base = sim if sim is not None else lexical
    if sim is None:
        concerns.append(_MODEL_UNAVAILABLE)

    final = base
    if opp.company.lower() in {c.lower() for c in profile.companies_prioritize}:
        matched.append("prioritized company")
        final = min(1.0, final + 0.15)
    # An opportunity whose employment type is one the user explicitly wants is a structural match,
    # independent of keyword overlap — a stipend program IS what a stipend-seeker wants even when its
    # generic description names no tech. (UNKNOWN never boosts — that would reward missing data.)
    if opp.employment_type != EmploymentType.UNKNOWN and opp.employment_type in set(profile.employment_types):
        matched.append(f"employment type wanted: {opp.employment_type.value}")
        final = min(1.0, final + 0.15)
    # eligibility nudge: a confident positive eligibility gets a small boost, unknown a small drag
    if opp.eligibility is not None:
        if opp.eligibility.category in (EligibilityCategory.WORLDWIDE_REMOTE, EligibilityCategory.STIPEND_PROGRAM_GLOBAL, EligibilityCategory.REMOTE_REGION_INCLUDES_USER):
            final = min(1.0, final + 0.05 * opp.eligibility.confidence)
        elif opp.eligibility.category == EligibilityCategory.UNKNOWN:
            final = max(0.0, final - 0.05)
    # Role-quality concerns dampen the score; the model-availability caveat is transparency, not a
    # defect of the role, so it must NOT silently dock every lexical-mode score.
    role_concerns = [c for c in concerns if c != _MODEL_UNAVAILABLE]
    final = max(0.0, final - 0.1 * len(role_concerns))

    return Relevance(score=round(final, 4), matched_signals=matched, concerns=concerns, semantic_similarity=sim)


# --------------------------------------------------------------------------------------------- #
# Hard filter + rank
# --------------------------------------------------------------------------------------------- #


def hard_filter(opps: list[Opportunity], profile: UserProfile, cfg: ScoringConfig, today: date | None = None) -> list[Opportunity]:
    """Drop opportunities disqualified by a HARD constraint. Binary, not a score penalty.

    Filters: confident-disqualifying eligibility, a deadline already passed, and an employment type
    the user explicitly does not want (UNKNOWN type is never dropped — that would penalize missing
    data). Runs BEFORE scoring so we never embed dead-on-arrival postings.
    """
    today = today or date.today()
    wanted = set(profile.employment_types)
    kept: list[Opportunity] = []
    for opp in opps:
        if opp.eligibility and opp.eligibility.is_confident_disqualifier(cfg.eligibility_disqualify_confidence):
            continue
        if opp.deadline and opp.deadline < today:
            continue
        if opp.employment_type != EmploymentType.UNKNOWN and wanted and opp.employment_type not in wanted:
            continue
        kept.append(opp)
    return kept


def rank(opps: list[Opportunity]) -> list[Opportunity]:
    """Eligibility gates rank first, then relevance. Implements 'known-eligible outranks unknown'."""

    def key(o: Opportunity):
        elig = _ELIGIBILITY_RANK.get(o.eligibility.category, 1) if o.eligibility else 1
        rel = o.relevance.score if o.relevance else 0.0
        return (-elig, -rel)

    return sorted(opps, key=key)
