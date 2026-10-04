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


# --------------------------------------------------------------------------------------------- #
# Stage fit (spec §12 S10) — can a current student meet the role's stated candidate stage? Rules with
# quoted evidence, like location eligibility. Carried in Relevance as "stage:" strings (no spine change).
# --------------------------------------------------------------------------------------------- #

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+|\s+[•·]\s+")
# Abbreviations whose dots must not end a sentence ("Ph.D. preferred", "e.g. Master's or PhD").
_ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|ph\.d|m\.sc|b\.sc|m\.s|b\.s|vs|incl|approx)\.", re.IGNORECASE)
_DOT = "\u2024"     # placeholder for a protected dot while splitting
_ADVANCED = re.compile(r"\b(ph\.?d|doctoral|m\.?sc|master'?s)\b", re.IGNORECASE)
# §12 lists these words in the singular; plurals are accepted ("MSc/PhD Internships … students").
_ADVANCED_CONTEXT = re.compile(
    r"\b(internships?|interns?|students?|candidates?|degrees?|enrolled|pursuing|required|must)\b", re.IGNORECASE)
# The exclusions are read near the degree mention, not across a whole tag-stripped list block (S10
# review M1): softening phrases within 60 chars; undergraduate/bachelor only as an alternative ("or",
# "and", "/") within 40 chars.
_ADVANCED_SOFT = re.compile(r"\b(high school|all backgrounds|or equivalent|preferred|a plus|nice to have)\b",
                            re.IGNORECASE)
_UNDERGRAD = re.compile(r"\b(undergraduates?|bachelor'?s?)\b", re.IGNORECASE)
_ALTERNATIVE = re.compile(r"\bor\b|\band\b|/", re.IGNORECASE)
# Company copy about the company, not a requirement ("founded by a team of PhD scientists").
_BLURB = re.compile(r"\b(founded|our mission|team of|our team|our founders?|our (users|customers|community))\b",
                    re.IGNORECASE)
_GRADUATE_BODY = (
    re.compile(r"\b(hiring|for)\s+(20\d\d\b[\s,and/&-]*)+\s*graduates?\b", re.IGNORECASE),
    re.compile(r"\b(must|will)\s+have\s+(graduated|completed\s+(a|your)\s+(bachelor|undergraduate|degree))",
               re.IGNORECASE),
    # "graduated" only: "graduating in May 2027" describes a current student (S10 review M4)
    re.compile(r"\bgraduated\s+(by|in|before|between)\s+\w+\s+20\d\d", re.IGNORECASE),
)
_EARLY_CAREER = re.compile(r"\b(early[- ]career|junior|students?|undergraduates?)\b", re.IGNORECASE)
_NEGATED = re.compile(r"\bnot\s+(eligible|open|accepted|considered)\b|\bineligible\b|\bcannot apply\b",
                      re.IGNORECASE)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                 "nine": 9, "ten": 10}
# A requirement-shaped years phrase: "<N>[+] [- M] years|yrs [of] [≤3 words] experience|hands-on". The
# spec's 60-char window with working/professional read company age, age limits and vesting (review H1).
_EXPERIENCE = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?|" + "|".join(_NUMBER_WORDS) + r")\s*\+?\s*(?:(?:[-–]|to)\s*\d+\s*)?"
    r"(?:years?|yrs?)\b(?:\s+of)?\s+(?:[\w/&-]+\s+){0,3}?(?:experience|hands-on)\b",
    re.IGNORECASE)
_COMPANY_SUBJECT = re.compile(r"\b(we|we've|our\s+\w+|founders?|company|team)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)
_FITS = re.compile(
    r"\b(students?|interns?|internships?|junior|jr\.?|early[- ]careers?|entry[- ]level|new[- ]grads?"
    r"|recent (?:university )?graduates?|trainees?|apprentices?)\b", re.IGNORECASE)
# A body sentence counts as stage evidence only when it addresses candidates (review M6).
_ADDRESSED = re.compile(
    r"\b(you|your|candidates?|applicants?|role|position|hiring|looking for|open to|apply|eligible|"
    r"we select|available to)\b", re.IGNORECASE)
NO_STAGE_EVIDENCE = "requirements not present in the feed text — check the posting"
STAGE_POSITIVE = frozenset({"fits", "stretch", "graduate_only_accepted"})


def _sentences(text: str) -> list[str]:
    t = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    t = _ABBREV.sub(lambda m: m.group(0).replace(".", _DOT), t)
    return [s.strip().replace(_DOT, ".") for s in _SENTENCE.split(t) if s.strip()]


def _advanced_requirement(s: str) -> bool:
    for m in _ADVANCED.finditer(s):
        win = s[max(0, m.start() - 60): m.end() + 60]
        near = s[max(0, m.start() - 40): m.end() + 40]
        if not _ADVANCED_CONTEXT.search(win) or _ADVANCED_SOFT.search(win) or _BLURB.search(win):
            continue
        if _UNDERGRAD.search(near) and _ALTERNATIVE.search(near):
            continue
        return True
    return False


def _years(s: str) -> list[float]:
    out = []
    for m in _EXPERIENCE.finditer(s):
        if _COMPANY_SUBJECT.search(s[: m.start()]):        # "we bring 25 years of experience"
            continue
        g = m.group(1).lower()
        out.append(float(_NUMBER_WORDS.get(g, g)))
    return out


def stage_fit(opp: Opportunity, profile: UserProfile) -> tuple[str, list[str]]:
    """(verdict, quoted evidence) — first match wins: advanced_degree → graduate_only →
    experience_required → stretch → fits → no_evidence. A bare "degree in Computer Science" is not
    graduate_only (most junior postings carry it). With no stage evidence the verdict says so."""
    from .normalize import _GRAD_PROGRAM_TITLE

    title = (opp.title or "").replace("\u2019", "'")
    sentences = _sentences(opp.description)

    advanced = [s for s in sentences if _advanced_requirement(s)]
    if advanced:
        return "advanced_degree", advanced[:2]

    title_early = bool(_EARLY_CAREER.search(title))       # incl. "Undergraduate/Graduate" titles
    if _GRAD_PROGRAM_TITLE.search(title) and not title_early:
        grad_ev = [s for s in sentences if any(rx.search(s) for rx in _GRADUATE_BODY)]
        return "graduate_only", [f"title: {title}", *grad_ev[:1]]

    def student_exception(s: str) -> bool:
        return bool(_EARLY_CAREER.search(s)) and not _NEGATED.search(s)

    grad = [s for s in sentences
            if any(rx.search(s) for rx in _GRADUATE_BODY) and not student_exception(s) and not title_early]
    if grad:
        return "graduate_only", grad[:2]

    years = [(n, s) for s in sentences for n in _years(s)]
    if years:
        n, s = max(years, key=lambda x: x[0])
        if n > profile.education.max_required_years:
            return "experience_required", [s]
        if n >= 1:
            return "stretch", [s]

    if _FITS.search(title):
        return "fits", [f"title: {title}"]
    fits = [s for s in sentences if _FITS.search(s) and _ADDRESSED.search(s) and not _NEGATED.search(s)]
    if fits:
        return "fits", fits[:1]
    return "no_evidence", [NO_STAGE_EVIDENCE]


def stage_signals(opp: Opportunity, profile: UserProfile) -> tuple[list[str], list[str]]:
    """(matched, concerns) entries carrying the stage verdict: "stage:<verdict>" then one
    'stage:evidence: "<sentence>"' per quote. A graduate-only role the profile accepts is recorded as
    `graduate_only_accepted` (positive) so the gate, which has no profile, can read it."""
    verdict, evidence = stage_fit(opp, profile)
    if verdict == "graduate_only" and profile.education.accept_graduate_programs:
        verdict = "graduate_only_accepted"
    entries = [f"stage:{verdict}", *(f'stage:evidence: "{e}"' for e in evidence)]
    return (entries, []) if verdict in STAGE_POSITIVE else ([], entries)


def stage_of(opp: Opportunity) -> tuple[str | None, list[str]]:
    """Read the stage verdict and evidence back from `opp.relevance` (None when not scored)."""
    r = opp.relevance
    if r is None:
        return None, []
    entries = [x for x in (*r.matched_signals, *r.concerns) if x.startswith("stage:")]
    verdict = next((x[len("stage:"):] for x in entries if not x.startswith("stage:evidence:")), None)
    evidence = [x[len('stage:evidence: "'):-1] for x in entries if x.startswith("stage:evidence:")]
    return verdict, evidence


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
    # Stage fit is a gate input, not a score input (§12: the score stays an ordering signal only).
    stage_matched, stage_concerns = stage_signals(opp, profile)
    matched += stage_matched
    concerns += stage_concerns

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
    r"(engineering|product|program|project|account|office) managers?|participants?|stud(y|ies)|"
    r"annotat(or|ion)|data entry|keyer|service desk|help ?desk|business development|social (growth|media)|"
    r"customer (research|service|experience)|opportunities|ad quality|professional services|needed|"
    r"financial|business analyst|operations analyst|mechanical|civil|chemical|policy|psychology|technician|guard)\b",
    re.IGNORECASE,
)


# Veto words that are never a team name, so they count anywhere in the title ("Research Assistant
# (Psychology)", "Mac Users Needed").
_DISCIPLINE_VETO = re.compile(
    r"\b(psychology|mechanical|civil|chemical|technician|guard|participants?|stud(y|ies)|needed|"
    r"data entry|keyer|annotat(or|ion))\b",
    re.IGNORECASE,
)
_TITLE_QUALIFIER = re.compile(r",\s|\s[-–—|]\s|\(|:\s")


def role_family_ok(title: str) -> bool:
    """True when the title names a technical role family and no non-technical veto word.

    The role head (text before the first ", " / " - " / "(") is judged on its own when it names a
    family, so a team-name suffix cannot veto it ("Backend Engineer Intern, People Platform" — final
    review M4). A head with no family word ("Intern, Software Engineering") falls back to the whole title.
    """
    title = title or ""
    head = _TITLE_QUALIFIER.split(title, maxsplit=1)[0]
    text = head if _ROLE_FAMILY.search(head) else title
    return (bool(_ROLE_FAMILY.search(text)) and not _ROLE_VETO.search(text)
            and not _DISCIPLINE_VETO.search(title))


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
