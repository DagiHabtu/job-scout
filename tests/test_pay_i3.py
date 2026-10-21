"""Iteration 3 §4.4 — pay as a dimension. Written before the code. Bodies named by label_id are the stored
texts (tests/fixtures/labels_2026-10-21_records.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.config import AppConfig, ScoringConfig, UserProfile
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity
from job_scout.notify import OUTSIDE_INTERESTS, gate_reason, render_issue_md, section_of
from job_scout.score import pay_of, score_opportunity

ROOT = Path(__file__).resolve().parents[1]
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))
REC = {r["label_id"]: r["record"] for r in _FX["records"]}
CFG = AppConfig.load(str(ROOT / "config" / "profile.yaml"))


def _opp(title, body, etype=ET.INTERNSHIP, company="X"):
    o = Opportunity(title=title, company=company, apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    employment_type=etype, status=Lifecycle.NEW, description=body)
    o.eligibility = Eligibility(EC.WORLDWIDE_REMOTE, 0.85, ["e"])
    return o


def _rec(label):
    r = REC[label]
    return _opp(r["title"], r["description"], company=r["company"])


@pytest.mark.parametrize("label,verdict,snippet", [
    ("holiday", "unpaid", None),
    ("flowai", "unpaid", None),
    ("makerble-devops", "unpaid", None),
    ("bridges", "unpaid", None),
    ("makerble-test", "contingent", None),
    ("vantum", "stated", "$500 to $1,000 USD per month"),
    ("flowmingo", "stipend", None),
    ("resilio", "stated", "35$/hr"),
])
def test_stored_bodies(label, verdict, snippet):
    v, s = pay_of(_rec(label))
    assert v == verdict, s
    if snippet is not None:
        assert s == snippet


@pytest.mark.parametrize("body,verdict", [
    ("Our team volunteers at local food banks.", "unstated"),
    # deviation: a budget is not pay (Canonical: "learning and development budget of USD 2,000 per year")
    ("Personal learning and development budget of USD 2,000 per year.", "unstated"),
    ("The pay is €2,500 per month.", "stated"),
    ("We pay USD 20/hour.", "stated"),
])
def test_body_shapes(body, verdict):
    assert pay_of(_opp("Software Engineer Intern", body))[0] == verdict


def test_unpaid_title():
    assert pay_of(_opp("Software Engineer Internship (UNPAID)", ""))[0] == "unpaid"


def test_gate_drops_unpaid_after_role_family_before_stage():
    o = _rec("holiday")
    o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
    assert gate_reason(o, 0.4) == "pay:unpaid"
    # a non-technical unpaid title is still role_family (checked first)
    o = _opp("Marketing Volunteer", "This is a volunteer role.")
    o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
    assert gate_reason(o, 0.4) == "role_family"


def test_accept_unpaid_keeps_it():
    profile = CFG.profile.model_copy(update={"pay": CFG.profile.pay.model_copy(update={"accept_unpaid": True})})
    o = _rec("holiday")
    o.relevance = score_opportunity(o, profile, ScoringConfig())
    assert gate_reason(o, 0.4) is None


def test_stipend_program_is_exempt():
    o = _opp("Open Source Fellowship", "This is an unpaid role.", etype=ET.STIPEND_PROGRAM)
    o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
    assert gate_reason(o, 0.4) is None


def test_profile_and_defaults():
    assert CFG.profile.pay.accept_unpaid is False
    assert UserProfile().pay.accept_unpaid is False
    assert "tester" in CFG.profile.not_interested


def test_outside_interests_paid_first_with_company_and_pay():
    vantum, other = _rec("vantum"), _opp("QA Intern", "Test our web app.", company="Other Co")
    for o in (vantum, other):
        o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
        assert section_of(o) == OUTSIDE_INTERESTS
    other.relevance.semantic_similarity, vantum.relevance.semantic_similarity = 0.9, 0.1   # title fit favours other
    md = render_issue_md([other, vantum], CFG)
    lines = [ln for ln in md.splitlines() if ln.startswith("- [ ]")]
    assert "QA Tester" in lines[0] and "Vantum" in lines[0] and "$500 to $1,000 USD per month" in lines[0]
    assert "Other Co" in lines[1]
