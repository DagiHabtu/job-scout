"""S10 independent review — each finding as a test (written before the fixes; see STATE.md)."""

from __future__ import annotations

import pytest

from job_scout.config import AppConfig, ScoringConfig, UserProfile
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity
from job_scout.notify import gate_reasons
from job_scout.score import score_opportunity, stage_fit

P = UserProfile()


def _v(title, body):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="u", description=body)
    return stage_fit(o, P)[0]


# H1 — years phrases that are not candidate requirements.
@pytest.mark.parametrize("body", [
    "Founded in 1999, we bring 25 years of experience serving clients.",
    "We have 10+ years working with Fortune 500 clients.",
    "Applicants must be at least 18 years old and eligible for working in the country.",
    "You must be 18 years of age or older to work with our professional team.",
    "Stock options vesting over 4 years, plus a professional development budget.",
    "Most juniors become leads within 3 years working here.",
    "Our 2,500 interns over 10 years working at the company say it best.",
])
def test_h1_non_requirement_years(body):
    assert _v("Junior Software Engineer", body) != "experience_required"


def test_h1_decimal_years():
    assert _v("Software Engineer", "1.5 years of experience with Python.") == "stretch"


def test_h1_boilerplate_does_not_beat_requirement():
    assert _v("Software Engineer", "0-1 years of experience. Our founders have 20 years of experience in fintech.") \
        != "experience_required"


def test_h1_real_requirements_still_caught():
    assert _v("Software Engineer", "You have 3+ years of professional experience with Go.") == "experience_required"
    assert _v("Software Engineer", "1+ years of hands-on Salesforce development or administration experience.") == "stretch"


# H2 — NEW_GRAD stage rejections appear in rejected_samples with their sentence.
def test_h2_new_grad_stage_rejection_is_sampled(tmp_path):
    from fixtures.gate0 import FakeSource
    from job_scout.models import RemoteStatus
    from job_scout.pipeline import run_once

    o = Opportunity(title="Graduate Software Engineer", company="X", apply_url="https://x/g", canonical_url="",
                    location_raw="Worldwide", remote_status=RemoteStatus.REMOTE,
                    description="We are hiring 2025 and 2026 Graduate Software Engineers into teams.")
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "s.db")
    cfg.notify.digest_path = str(tmp_path / "d.html")
    cfg.profile.employment_types.append(ET.NEW_GRAD)          # as in config/profile.yaml
    s = run_once(cfg, [FakeSource("fake", [o])])
    assert s.gate == {"stage:graduate_only": 1}
    samples = s.internship_funnel["rejected_samples"]
    assert samples and samples[0]["reason"] == "stage:graduate_only" and "2026 Graduate" in samples[0]["evidence"]


# M1 — sentence boundaries: real requirement blocks and abbreviations.
TETHER_REQ = ("Requirements MSc/PhD candidate in computer science or a related technical discipline Related Research "
              "Experience at least one of the following areas: LLM, computer vision, multimodality Be proficient with "
              "PyTorch deep learning framework and libraries Have excellent analytical and problem-solving skills, "
              "logical thinking skills, communication and collaboration skills Publications in the top AI conferences "
              "(e.g., ACL, NIPS, ICML, ICLR, CVPR, ICCV, ECCV, TPAMI, IJCV, etc.) is a nice to have.")


def test_m1_tether_real_requirements_block_is_advanced():
    assert _v("Research Engineer Intern (Video/Multimodal LLM)", TETHER_REQ) == "advanced_degree"


def test_m1_enrolled_phd_in_merged_list():
    body = "Requirements Currently enrolled in a PhD program Strong Python skills Bachelor's degree in CS"
    assert _v("Research Engineer Intern", body) == "advanced_degree"


@pytest.mark.parametrize("body", [
    "Candidates with a Ph.D. are preferred.",
    "Students pursuing a Ph.D. in ML are a plus.",
    "We're open to people of all backgrounds (e.g. self-taught, Master's or PhD degree).",
])
def test_m1_abbreviations_keep_the_softener(body):
    assert _v("Research Intern", body) != "advanced_degree"


# M2 — company boilerplate is not an MSc/PhD requirement.
@pytest.mark.parametrize("body", [
    "Founded by a team of PhD scientists, we are looking for candidates who love to learn.",
    "Our mission is to help every student get a master's degree.",
])
def test_m2_boilerplate_not_advanced(body):
    assert _v("Junior Software Engineer", body) != "advanced_degree"


# M3 / L3 — titles that are not graduate-only programs.
@pytest.mark.parametrize("title", [
    "Software Engineering Intern (Undergraduate/Graduate)",
    "Graduate or Undergraduate Software Intern",
    "Graduate Research Assistant",
    "Graduate Teaching Assistant",
])
def test_m3_l3_not_graduate_only_titles(title):
    assert _v(title, "") != "graduate_only"


# M4 — a future graduation date means a current student.
@pytest.mark.parametrize("body", [
    "Candidates graduating between December 2026 and June 2027 are eligible.",
    "Applicants graduating in May 2027 are eligible.",
    "Open for 2026 graduates and undergraduates.",
])
def test_m4_current_students_not_graduate_only(body):
    assert _v("Software Engineer Intern", body) != "graduate_only"


def test_m4_completed_degree_still_graduate_only():
    assert _v("Software Engineer", "You must have graduated by June 2026.") == "graduate_only"


# M5 — a negated student mention is not the exception and not a fit.
def test_m5_negated_students():
    body = "Applicants must have graduated before starting; current students are not eligible."
    assert _v("Associate Software Engineer", body) == "graduate_only"


# M6 — boilerplate mentioning students is not stage evidence.
@pytest.mark.parametrize("body", [
    "Our learning app is used by 2 million students worldwide.",
    "Our community represents the full breadth of the developer experience; from students, hobbyists and "
    "freelancers to high performance engineering teams.",
])
def test_m6_boilerplate_students_is_no_evidence(body):
    assert _v("Software Engineer", body) == "no_evidence"


def test_m6_candidate_sentence_still_fits():
    body = "We select candidates that are recent university graduates or early career professionals."
    assert _v("Kernel Engineer - Ubuntu", body) == "fits"


# L1 / L2 — word numbers, "yrs", curly apostrophe.
@pytest.mark.parametrize("body,verdict", [
    ("Five years of professional experience with Go.", "experience_required"),
    ("Two years of experience with Python.", "stretch"),
    ("3+ yrs of professional experience.", "experience_required"),
])
def test_l1_word_numbers_and_yrs(body, verdict):
    assert _v("Software Engineer", body) == verdict


def test_l2_curly_apostrophe():
    assert _v("Research Intern", "Master’s students only, enrolled at a university.") == "advanced_degree"


# Weak-test gap — the two caps act on separate groups.
def test_caps_interaction():
    body = "MSc/PhD Internships at Tether aim to provide students with research opportunities."

    def mk(i, cat):
        o = Opportunity(title=f"Research Engineer Intern {i}", company="X", apply_url=f"u{i}", canonical_url=f"u{i}",
                        description=body, employment_type=ET.INTERNSHIP, status=Lifecycle.NEW)
        o.eligibility = Eligibility(cat, 0.85, ["e"])
        o.relevance = score_opportunity(o, P, ScoringConfig())
        return o

    opps = [mk(i, EC.WORLDWIDE_REMOTE) for i in range(3)] + [mk(10 + i, EC.UNKNOWN) for i in range(6)]
    r = gate_reasons(opps, 0.4)
    assert r[:3].count(None) == 2 and r[:3].count("stage:advanced_cap") == 1
    assert r[3:].count(None) == 5 and r[3:].count("unknown_cap") == 1


# L6 — the HTML digest shows a readable stage line, never raw "stage:" strings; none for programs.
def test_l6_digest_stage_rendering():
    from job_scout.notify import render_digest

    o = Opportunity(title="CRM Developer", company="X", apply_url="u", canonical_url="u",
                    description="1+ years of hands-on Salesforce development experience.", employment_type=ET.NEW_GRAD)
    o.relevance = score_opportunity(o, P, ScoringConfig())
    html = render_digest([o], AppConfig())
    assert "stage: <b>stretch</b>" in html and "stage:evidence" not in html and "stage:stretch" not in html
    prog = Opportunity(title="Outreachy", company="O", apply_url="u2", canonical_url="u2", description="",
                       employment_type=ET.STIPEND_PROGRAM)
    prog.relevance = score_opportunity(prog, P, ScoringConfig())
    assert "stage:" not in render_digest([prog], AppConfig())
