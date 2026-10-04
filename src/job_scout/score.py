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
from .normalize import _SENIOR_TITLE
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


def embed_similarity(opp: Opportunity, profile: UserProfile, model) -> float | None:
    """Max cosine between the TITLE and each target role. Title only: descriptions start with
    employer boilerplate that the model's 256-token window never gets past (C3)."""
    if model is None or not profile.target_roles:
        return None
    try:  # pragma: no cover - only where a real model is present
        import numpy as np

        vecs = model.encode([opp.title, *profile.target_roles], normalize_embeddings=True)
        return float(np.max(vecs[1:] @ vecs[0]))
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
    # Target technologies named in the body: +0.03 each, capped at +0.15.
    body = f"{opp.description} {' '.join(opp.technologies)}".lower()
    body_tech = [t for t in profile.target_technologies if _wb(t, body)]
    if body_tech:
        final = min(1.0, final + min(0.15, 0.03 * len(body_tech)))
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
    # No per-concern damping: seniority is a hard filter now (S4); concerns stay listed for the reader.

    return Relevance(score=round(final, 4), matched_signals=matched, concerns=concerns, semantic_similarity=sim)


# --------------------------------------------------------------------------------------------- #
# Role family — is this title the kind of work the user targets? (pure regex, testable in CI)
# --------------------------------------------------------------------------------------------- #

# Spec S5 regexes, extended after the golden set (tests/fixtures/golden_titles.csv) measured the exact
# spec version at precision 0.61: the extra veto terms each come from a mislabelled golden row (paid
# "AI study" posts, data entry/annotation, service desk, managers); the extra family terms from
# missed technical titles. See STATE.md "Deviations from spec".
_ROLE_FAMILY = re.compile(
    r"\b(engineer(ing)?|developer|programmer|software|data|machine learning|ml|ai|devops|sre|"
    r"site reliability|platform|infrastructure|cloud|backend|back-end|full[- ]?stack|analyst|analytics|"
    r"scientist|security|qa|research|"
    r"embedded|computer vision|database)\b",
    re.IGNORECASE,
)
_ROLE_VETO = re.compile(
    r"\b(sales|account executive|marketing|recruit(er|ing)|talent|legal|counsel|finance|accounting|"
    r"customer success|people|hr|designer?|content|community|partnerships?|curriculum|renewals|support|"
    r"manager|participants?|stud(y|ies)|annotat(or|ion)|data entry|keyer|service desk|help ?desk|"
    r"business development|social|customer|opportunities|ad quality|professional services)\b",
    re.IGNORECASE,
)


def role_family_ok(title: str) -> bool:
    """True when the title names a technical role family and no non-technical veto word."""
    return bool(_ROLE_FAMILY.search(title or "")) and not _ROLE_VETO.search(title or "")


# --------------------------------------------------------------------------------------------- #
# Hard filter + rank
# --------------------------------------------------------------------------------------------- #


def filter_reason(opp: Opportunity, profile: UserProfile, cfg: ScoringConfig, today: date | None = None) -> str | None:
    """The first HARD constraint `opp` fails, as a reason code — or None if it survives.

    Codes: `eligibility:<category>` (a confident disqualifier), `deadline_passed`,
    `type_unwanted:<type>` (a known type the user does not want; UNKNOWN is never dropped — that
    would penalize missing data). One record → at most one reason, so reasons can be counted.
    """
    today = today or date.today()
    wanted = set(profile.employment_types)
    if opp.eligibility and opp.eligibility.is_confident_disqualifier(cfg.eligibility_disqualify_confidence):
        return f"eligibility:{opp.eligibility.category.value}"
    if opp.deadline and opp.deadline < today:
        return "deadline_passed"
    if opp.employment_type != EmploymentType.UNKNOWN and wanted and opp.employment_type not in wanted:
        return f"type_unwanted:{opp.employment_type.value}"
    # A seniority token in the title is high-precision and never actionable for this profile. An
    # internship/program title may name a senior person ("Intern, Engineering Manager's Office").
    if opp.employment_type not in (EmploymentType.INTERNSHIP, EmploymentType.STIPEND_PROGRAM):
        m = _SENIOR_TITLE.search(opp.title or "")
        if m:
            return f"seniority_title:{m.group(1).lower()}"
    return None


def hard_filter(opps: list[Opportunity], profile: UserProfile, cfg: ScoringConfig, today: date | None = None) -> list[Opportunity]:
    """Drop opportunities disqualified by a HARD constraint (see `filter_reason`). Binary, not a
    score penalty. Runs BEFORE scoring so we never embed dead-on-arrival postings."""
    today = today or date.today()
    return [o for o in opps if filter_reason(o, profile, cfg, today) is None]


def rank(opps: list[Opportunity]) -> list[Opportunity]:
    """Eligibility gates rank first, then relevance. Implements 'known-eligible outranks unknown'."""

    def key(o: Opportunity):
        elig = _ELIGIBILITY_RANK.get(o.eligibility.category, 1) if o.eligibility else 1
        rel = o.relevance.score if o.relevance else 0.0
        return (-elig, -rel)

    return sorted(opps, key=key)
