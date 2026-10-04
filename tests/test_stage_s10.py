"""S10 — stage fit (candidate-stage eligibility), spec §12. Written before the implementation."""

from __future__ import annotations

from datetime import datetime

import pytest

from job_scout.config import AppConfig, ScoringConfig, UserProfile
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity
from job_scout.normalize import _GRAD_PROGRAM_TITLE, infer_employment_type
from job_scout.notify import gate_reason, gate_reasons, render_issue_md, section_of
from job_scout.score import score_opportunity, stage_fit, stage_of

P = UserProfile()


def _o(title="Software Engineer Intern", body="", etype=ET.INTERNSHIP, cat=EC.WORLDWIDE_REMOTE):
    o = Opportunity(title=title, company="X", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    description=body, employment_type=etype, status=Lifecycle.NEW)
    o.eligibility = Eligibility(cat, 0.85, ["worldwide"])
    return o


# --- stage_fit table: the four real sentences from the 2026-10-04 run (§12) -------------------- #
REAL = [
    ("Research Engineer Intern (Video/Multimodal LLM)",
     "We are looking for talented individuals to join us for an internship in 2025/2026. MSc/PhD Internships at "
     "Tether aim to provide students with the opportunity to actively contribute to our products and research.",
     "advanced_degree"),
    ("Graduate Software Engineer, Open Source and Linux, Canonical Ubuntu",
     "We are hiring 2025 and 2026 Graduate Software Engineers into engineering teams around the world.",
     "graduate_only"),
    ("CRM Developer", "1+ years of hands-on Salesforce development or administration experience.", "stretch"),
    ("Junior Linux Kernel Engineer - Ubuntu",
     "We select candidates that are recent university graduates or early career professionals. These are "
     "full-time positions available to prospective or recently graduated students.", "fits"),
    ("Junior Ubuntu Software Engineer",
     "Our junior career path caters for both new graduates and early careers engineers.", "fits"),
    ("Software Engineer Intern",
     "We're open to exceptional people of all backgrounds for research (e.g. high school, undergraduate and "
     "postgraduate degree).", "fits"),
]


@pytest.mark.parametrize("title,body,verdict", REAL)
def test_stage_fit_real_sentences(title, body, verdict):
    v, ev = stage_fit(_o(title, body), P)
    assert v == verdict
    if verdict in ("advanced_degree", "graduate_only", "stretch"):
        assert ev and all(isinstance(s, str) and s for s in ev)


@pytest.mark.parametrize("title,body,not_verdict", [
    ("Junior Software Engineer", "Bachelor's degree in CS or equivalent experience.", "graduate_only"),
    ("Research Intern", "PhD preferred but not required for this internship.", "advanced_degree"),
    ("Undergraduate Software Engineering Intern", "", "graduate_only"),
    ("Junior Software Engineer", "We have been 5 years in business and keep growing.", "experience_required"),
    ("Junior Software Engineer", "A degree in Computer Science is required.", "graduate_only"),
    ("Research Intern", "Open to undergraduate or Master's students pursuing a degree.", "advanced_degree"),
])
def test_stage_fit_negatives(title, body, not_verdict):
    assert stage_fit(_o(title, body), P)[0] != not_verdict


@pytest.mark.parametrize("body,verdict", [
    ("You have 3+ years of professional experience with Go.", "experience_required"),
    ("2-4 years of working experience required.", "stretch"),          # largest N captured is 2
    ("At least 5 years experience building backends.", "experience_required"),
    ("You must have graduated by June 2026.", "graduate_only"),
    ("Candidates graduating in May 2026 are welcome.", "graduate_only"),
    ("You will have completed a bachelor's degree before starting.", "graduate_only"),
])
def test_stage_fit_rules(body, verdict):
    assert stage_fit(_o("Software Engineer", body, etype=ET.NEW_GRAD), P)[0] == verdict


def test_graduate_rule_unless_same_sentence_names_students():
    v, _ = stage_fit(_o("Software Engineer", "We are hiring 2026 graduates and students for this role."), P)
    assert v != "graduate_only"


def test_no_evidence():
    v, ev = stage_fit(_o("Software Engineer", "Build things with us.", etype=ET.NEW_GRAD), P)
    assert v == "no_evidence" and "requirements not present in the feed text" in " ".join(ev)


# --- normalize split ----------------------------------------------------------------------------- #
@pytest.mark.parametrize("title,match", [
    ("Graduate Software Engineer", True), ("New Grad Backend Engineer", True), ("Recent Graduate Analyst", True),
    ("Undergraduate Research Intern", False), ("Graduate Student Researcher", False),
    ("Graduate Degree Program Engineer", False), ("Junior Software Engineer", False),
])
def test_grad_program_title(title, match):
    assert bool(_GRAD_PROGRAM_TITLE.search(title)) is match


def test_graduate_title_still_typed_new_grad():
    o = Opportunity(title="Graduate Software Engineer", company="X", apply_url="u", canonical_url="u")
    assert infer_employment_type(o) == ET.NEW_GRAD


# --- carried in Relevance, read by the gate -------------------------------------------------------- #
def _scored(title, body, etype=ET.NEW_GRAD, cat=EC.WORLDWIDE_REMOTE, profile=P):
    o = _o(title, body, etype, cat)
    o.relevance = score_opportunity(o, profile, ScoringConfig())
    return o


def test_stage_strings_in_relevance():
    o = _scored("Graduate Software Engineer", "We are hiring 2026 graduates.")
    v, ev = stage_of(o)
    assert v == "graduate_only" and any(s.startswith("stage:") for s in o.relevance.concerns)


def test_gate_graduate_only_and_experience():
    assert gate_reason(_scored("Graduate Software Engineer", "We are hiring 2026 graduates."), 0.4) == "stage:graduate_only"
    assert gate_reason(_scored("Junior Software Engineer", "5+ years of professional experience."), 0.4) == "stage:experience"


def test_accept_graduate_programs_lets_them_through():
    p = UserProfile(education={"status": "graduate", "accept_graduate_programs": True, "max_required_years": 2})
    assert gate_reason(_scored("Graduate Software Engineer", "We are hiring 2026 graduates.", profile=p), 0.4) is None


def test_max_required_years_from_profile():
    p = UserProfile(education={"max_required_years": 3})
    assert stage_fit(_o("Junior Software Engineer", "3+ years of professional experience."), p)[0] == "stretch"


def test_advanced_degree_is_aspirational_capped_at_two():
    body = "MSc/PhD Internships at Tether aim to provide students with research opportunities."
    opps = [_scored(f"Research Engineer Intern {i}", body, etype=ET.INTERNSHIP) for i in range(3)]
    reasons = gate_reasons(opps, 0.4)
    assert reasons.count(None) == 2 and reasons.count("stage:advanced_cap") == 1
    assert section_of(opps[0]) == "Aspirational"


def test_advanced_degree_with_unknown_eligibility_is_not_aspirational():
    body = "MSc/PhD Internships at Tether aim to provide students with research opportunities."
    o = _scored("Research Engineer Intern", body, etype=ET.INTERNSHIP, cat=EC.UNKNOWN)
    assert gate_reason(o, 0.4) is None and section_of(o) == "Check eligibility"


def test_stipend_programs_skip_stage():
    o = _scored("Outreachy — applications open", "We are hiring 2026 graduates.", etype=ET.STIPEND_PROGRAM,
                cat=EC.STIPEND_PROGRAM_GLOBAL)
    assert gate_reason(o, 0.4) is None


def test_issue_shows_stage_verdict_and_sentence():
    o = _scored("CRM Developer", "1+ years of hands-on Salesforce development or administration experience.")
    md = render_issue_md([o], AppConfig())
    assert "stage: **stretch**" in md and "1+ years of hands-on Salesforce" in md
    assert "matched: stage:" not in md


def test_pipeline_stage_rejection_sample_quotes_sentence(tmp_path):
    from fixtures.gate0 import FakeSource
    from job_scout.models import RemoteStatus
    from job_scout.pipeline import run_once

    o = Opportunity(title="Graduate Software Engineer Intern Program", company="X", apply_url="https://x/g",
                    canonical_url="", location_raw="Worldwide", remote_status=RemoteStatus.REMOTE,
                    description="We are hiring 2026 graduates into our teams.")
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "s.db")
    cfg.notify.digest_path = str(tmp_path / "d.html")
    s = run_once(cfg, [FakeSource("fake", [o])])
    assert s.gate == {"stage:graduate_only": 1} and s.notified == 0
    sample = s.internship_funnel["rejected_samples"][0]
    assert sample["reason"] == "stage:graduate_only" and "hiring 2026 graduates" in sample["evidence"]
