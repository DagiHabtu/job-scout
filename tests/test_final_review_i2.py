"""Iteration-2 final review — each finding as a test, written before the fixes (see STATE.md), with Dagi's
decisions of 2026-10-04 on how to resolve them (numbered D1–D7 below)."""

from __future__ import annotations

from pathlib import Path

import pytest

from job_scout.config import AppConfig, ScoringConfig
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity
from job_scout.notify import gate_reasons, render_heartbeat_md, render_issue_md, section_of
from job_scout.score import score_opportunity, stage_fit

ROOT = Path(__file__).resolve().parents[1]
PROFILE = AppConfig.load(ROOT / "config" / "profile.yaml").profile
APPLY, CHECK, ASPIRATIONAL, OUTSIDE = "Apply", "Check eligibility", "Aspirational", "Eligible, outside your stated interests"


def _scored(title, etype=ET.INTERNSHIP, cat=EC.WORLDWIDE_REMOTE, body=""):
    o = Opportunity(title=title, company="X", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    description=body, employment_type=etype, status=Lifecycle.NEW)
    o.eligibility = Eligibility(cat, 0.85 if cat != EC.UNKNOWN else 0.4, ["evidence"])
    o.relevance = score_opportunity(o, PROFILE, ScoringConfig())
    return o


def _verdict(title, body, etype=ET.NEW_GRAD):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="u", description=body, employment_type=etype)
    return stage_fit(o, PROFILE)[0]


# H1 / D1 — every "N years" mention is a requirement unless its sentence is about something else.
@pytest.mark.parametrize("body", [
    "We require 3+ years of experience with Go.",
    "We expect 5 years of hands-on experience.",
    "Our ideal candidate has 4+ years of experience building APIs.",
    "Minimum 3 years' experience in backend development.",
    "You have 3+ years working with Kubernetes in production.",
    "5+ years of professional software development.",
    "At least 4 years in a backend role.",
])
def test_h1_requirement_wordings_reject_junior(body):
    o = _scored("Junior Backend Engineer", ET.NEW_GRAD, body=body)
    assert gate_reasons([o], 0.4) == ["stage:experience"], body


# M4 / D1 — sentences about something else (combined/team experience, company age or history).
@pytest.mark.parametrize("body", [
    "We are a team of 5 with 20 years of combined experience.",
    "We have been in business for 15 years.",
    "Acme was founded 12 years ago and serves 300 clients.",
    "Our engineers have a track record of 10 years shipping kernels.",
])
def test_m4_non_requirement_years(body):
    assert _verdict("Junior Backend Engineer", body) != "experience_required", body


# D1 measured on the stored descriptions (data/scout.db, 2026-10-04): real sentences either way.
@pytest.mark.parametrize("body,required", [
    ("Who you are Proven track record of at least 3 years of professional software development using Go or C++.", True),
    ("Your skill-set: 3+ years in outbound sales development / prospecting, with a track record of pipeline.", True),
    ("At least 2 to 4 years of professional software engineering experience post University.", False),   # N=2 (L6)
    ("Who can participate: Adults 18 years and older Comfortable being recorded on video.", False),
    ("Essential Qualifications: Minimum age: 18 years English fluency.", False),
    ("All Right is a leading Ukrainian IT company that has been helping children worldwide learn English with "
     "ease and enjoyment for 8 years!", False),
    ("Ensure their work reaches the widest audience, with a 10 year enterprise security commitment.", False),
])
def test_d1_stored_sentences(body, required):
    assert (_verdict("Junior Software Engineer", body) == "experience_required") is required, body


def test_m4_intern_with_combined_experience_reaches_apply():
    o = _scored("Software Engineering Intern", body="We are a team of 5 with 20 years of combined experience.")
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == APPLY


# D2 — internships are exempt from the experience gate; the years sentence is shown as a note.
def test_d2_internship_years_is_a_note_not_a_rejection():
    body = "You have 3+ years of experience with Go."
    o = _scored("Software Engineer Intern", body=body)
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == APPLY
    assert body in render_issue_md([o], AppConfig())


# M3 / D3 — least actionable section wins; "Check eligibility" holds only would-be "Apply" roles.
def test_d3_unknown_advanced_degree_is_aspirational_with_note():
    o = _scored("Software Engineer Intern", cat=EC.UNKNOWN,
                body="Currently pursuing a Master's or PhD in Computer Science.")
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == ASPIRATIONAL
    md = render_issue_md([o], AppConfig())
    assert "eligibility not confirmed" in md


def test_d3_unknown_vetoed_is_outside_interests():
    o = _scored("QA Intern", cat=EC.UNKNOWN, body="Test our web app across browsers and report bugs.")
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == OUTSIDE


def test_d3_caps_act_per_section():
    msc = "Currently pursuing a Master's or PhD in Computer Science."
    asp = [_scored(f"Research Engineer Intern {i}", cat=EC.UNKNOWN, body=msc) for i in range(3)]
    chk = [_scored(f"Software Engineer Intern {i}", cat=EC.UNKNOWN) for i in range(6)]
    r = gate_reasons(asp + chk, 0.4)
    assert r[:3].count(None) == 2 and r[:3].count("stage:advanced_cap") == 1
    assert r[3:].count(None) == 5 and r[3:].count("unknown_cap") == 1


# M2 / D4 — role family is checked before the interest veto: non-technical titles are not selected.
@pytest.mark.parametrize("title,etype,body", [
    ("QC Inspector Intern", ET.INTERNSHIP, "Inspect incoming materials on the production line."),
    ("Quality Assurance Intern", ET.INTERNSHIP,
     "Support GMP compliance, review batch records and laboratory documentation at our pharmaceutical site."),
    ("CRM Intern", ET.INTERNSHIP, "Support our sales team in HubSpot: update contacts and log calls."),
    ("Junior CRM Specialist", ET.NEW_GRAD, "Keep our customer records tidy in HubSpot."),
    ("CRM Assistant (with Insellerate Experience)", ET.NEW_GRAD, "Assist loan officers with CRM data."),
])
def test_m2_non_technical_vetoed_titles_are_role_family(title, etype, body):
    assert gate_reasons([_scored(title, etype, body=body)], 0.4) == ["role_family"], title


def test_m2_software_qa_still_reaches_outside_interests():
    o = _scored("QA/QC Intern", body="You will test our AI interview flow across mobile devices and browsers.")
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == OUTSIDE


# M1 / D5 — a strong term cancels the veto and the title is technical → "Apply" with the note.
@pytest.mark.parametrize("title", ["QA Intern, Linux Kernel", "QA (Linux) Intern"])
def test_m1_strong_term_reaches_apply_with_note(title):
    o = _scored(title)
    assert gate_reasons([o], 0.4) == [None] and section_of(o) == APPLY
    assert "matches 'qa' but also 'linux'" in render_issue_md([o], AppConfig())


# M5 / D6 — a softener anywhere after the degree in the same sentence.
@pytest.mark.parametrize("body", [
    "PhD students are welcome to apply for this internship on our compiler and runtime team, though a PhD is a "
    "plus rather than a requirement.",
    "Candidates pursuing a PhD in machine learning, statistics, applied mathematics or a related quantitative "
    "field are preferred.",
])
def test_m5_softener_after_degree(body):
    assert _verdict("Research Intern", body, ET.INTERNSHIP) != "advanced_degree"


# M6 / D7 — at least 2 sample slots go to stage rejections, per run and in the weekly heartbeat.
def test_m6_stage_rejections_reserved_in_run_samples():
    from job_scout.pipeline import _internship_funnel

    opps = [_scored(f"Intern {i}") for i in range(7)]
    reasons = ["interest:cap", "interest:cap", "stage:advanced_cap", "stage:advanced_cap", "unknown_cap",
               "stage:graduate_only", "stage:experience"]
    f = _internship_funnel(opps, {id(o) for o in opps}, {id(o): r for o, r in zip(opps, reasons)})
    got = [s["reason"] for s in f["rejected_samples"]]
    assert len(got) == 5 and {"stage:graduate_only", "stage:experience"} <= set(got)


def test_m6_heartbeat_lists_samples_with_stage_reserve():
    def rec(samples):
        return {"run_id": "r", "started": "2026-10-04T00:00:00", "discovered": 1, "after_filter": 1, "notified": 0,
                "sources": {}, "internship_funnel": {"fetched": 1, "outcomes": {}, "rejected_samples": samples}}

    def s(t, reason, ev=""):
        return {"title": t, "company": "X", "location": "", "reason": reason, "evidence": ev}

    records = [rec([s(f"A{i}", "interest:cap") for i in range(5)]),
               rec([s(f"B{i}", "unknown_cap") for i in range(4)] + [s("G", "stage:graduate_only", "hiring 2026 graduates")]),
               rec([s("E", "stage:experience", "5+ years of Go")])]
    md = render_heartbeat_md(records)
    assert "hiring 2026 graduates" in md and "5+ years of Go" in md


# L1 — a stipend program never prints the "outside your stated interests" line.
def test_l1_stipend_program_no_interest_line():
    o = _scored("Salesforce Trailblazer Fellowship", ET.STIPEND_PROGRAM, cat=EC.STIPEND_PROGRAM_GLOBAL)
    md = render_issue_md([o], AppConfig())
    assert section_of(o) == APPLY and "outside your stated interests" not in md
