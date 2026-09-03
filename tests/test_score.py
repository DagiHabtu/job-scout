"""Scoring, hard-filtering, and ranking — the lexical (no-model) path and the eligibility gate."""

from __future__ import annotations

from datetime import date, timedelta

from job_scout.config import ScoringConfig, UserProfile
from job_scout.models import (
    Eligibility,
    EligibilityCategory as EC,
    EmploymentType,
    Opportunity,
    Relevance,
)
from job_scout.score import hard_filter, lexical_signals, rank, score_opportunity


def _opp(**kw) -> Opportunity:
    base = dict(title="Backend Intern", company="Globex", apply_url="https://x/1", canonical_url="")
    base.update(kw)
    return Opportunity(**base)


PROFILE = UserProfile(
    target_roles=["backend intern"],
    target_technologies=["python", "sql", "docker"],
    keywords_prioritize=["open source"],
    keywords_penalize=["senior"],
)
CFG = ScoringConfig()


def test_lexical_signals_reward_matches_and_flag_penalties():
    matched, concerns, score = lexical_signals(
        _opp(description="Backend intern working in Python and SQL. Open source friendly."), PROFILE
    )
    assert any("python" in m.lower() for m in matched)
    assert any("role match" in m.lower() for m in matched)
    assert 0.0 < score <= 1.0
    # a penalize keyword in the TITLE flags a concern; the same word in prose does NOT (title-scoped)
    _, title_concerns, _ = lexical_signals(_opp(title="Senior Backend Engineer", description="Python role."), PROFILE)
    assert any("senior" in c.lower() for c in title_concerns)
    _, prose_concerns, _ = lexical_signals(
        _opp(title="Backend Intern", description="You will work alongside senior engineers."), PROFILE
    )
    assert not any("senior" in c.lower() for c in prose_concerns)


def test_word_boundary_prevents_substring_false_matches():
    prof = UserProfile(target_technologies=["go"], target_roles=[])
    # 'go' must not match inside 'category' / 'goal'
    matched, _, score = lexical_signals(_opp(description="We categorize goals across the org."), prof)
    assert not matched and score == 0.0
    matched2, _, _ = lexical_signals(_opp(description="Backend services written in Go."), prof)
    assert any("go" in m.lower() for m in matched2)


def test_score_without_model_falls_back_to_lexical_and_flags_it():
    rel = score_opportunity(_opp(description="Backend intern in Python, SQL, Docker."), PROFILE, CFG, model=None)
    assert rel.semantic_similarity is None
    assert 0.0 <= rel.score <= 1.0
    assert any("model unavailable" in c.lower() for c in rel.concerns)


def test_score_boosts_prioritized_company():
    prof = UserProfile(target_technologies=["python"], companies_prioritize=["Globex"])
    boosted = score_opportunity(_opp(description="Python role."), prof, CFG, model=None)
    assert any("prioritized company" in m.lower() for m in boosted.matched_signals)


def test_wanted_employment_type_boosts_score():
    prof = UserProfile(target_technologies=["python"], employment_types=[EmploymentType.INTERNSHIP])
    intern = _opp(employment_type=EmploymentType.INTERNSHIP, description="A generic role description.")
    unknown = _opp(employment_type=EmploymentType.UNKNOWN, description="A generic role description.")
    s_i = score_opportunity(intern, prof, CFG, model=None)
    s_u = score_opportunity(unknown, prof, CFG, model=None)
    assert s_i.score > s_u.score
    assert any("employment type wanted" in m.lower() for m in s_i.matched_signals)


def test_hard_filter_drops_confident_disqualifier():
    opp = _opp(eligibility=Eligibility(EC.REQUIRES_WORK_AUTH, 0.85))
    assert hard_filter([opp], PROFILE, CFG) == []


def test_hard_filter_keeps_low_confidence_disqualifier():
    # Below the disqualify threshold → surfaced, not dropped.
    opp = _opp(eligibility=Eligibility(EC.REQUIRES_WORK_AUTH, 0.5))
    assert hard_filter([opp], PROFILE, CFG) == [opp]


def test_hard_filter_drops_passed_deadline():
    opp = _opp(deadline=date.today() - timedelta(days=1))
    assert hard_filter([opp], PROFILE, CFG, today=date.today()) == []


def test_hard_filter_drops_unwanted_employment_type_but_keeps_unknown():
    prof = UserProfile(employment_types=[EmploymentType.INTERNSHIP, EmploymentType.STIPEND_PROGRAM])
    full_time = _opp(employment_type=EmploymentType.FULL_TIME)
    unknown = _opp(employment_type=EmploymentType.UNKNOWN)      # missing data is never penalized
    intern = _opp(employment_type=EmploymentType.INTERNSHIP)
    kept = hard_filter([full_time, unknown, intern], prof, CFG)
    assert full_time not in kept
    assert unknown in kept and intern in kept


def test_rank_puts_eligibility_before_relevance():
    # Known-eligible (WORLDWIDE) must outrank a more-relevant UNKNOWN — the core eligibility gate.
    unknown_hi = _opp(title="A", eligibility=Eligibility(EC.UNKNOWN, 0.3), relevance=Relevance(score=0.9))
    world_lo = _opp(title="B", eligibility=Eligibility(EC.WORLDWIDE_REMOTE, 0.8), relevance=Relevance(score=0.4))
    world_hi = _opp(title="C", eligibility=Eligibility(EC.WORLDWIDE_REMOTE, 0.8), relevance=Relevance(score=0.8))
    ordered = rank([unknown_hi, world_lo, world_hi])
    assert [o.title for o in ordered] == ["C", "B", "A"]
