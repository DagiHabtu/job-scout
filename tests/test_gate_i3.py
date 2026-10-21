"""Iteration 3 §4.2 — the "unverified" gate tier. Written before the code.

Unverified = eligibility UNKNOWN with confidence ≥ 0.6 (the aggregator marker with a silent body). It is
selected for INTERNSHIP and NEW_GRAD into "Check eligibility" — surfaced as uncertain, never as eligible.
"""

from __future__ import annotations

import pytest

from job_scout import _geo
from job_scout.config import AppConfig, ScoringConfig
from job_scout.eligibility import classify_eligibility
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity, RemoteStatus
from job_scout.notify import CHECK_ELIGIBILITY, gate_reason, render_issue_md, section_of
from job_scout.score import score_opportunity

CFG = AppConfig()


def _opp(etype, cat=EC.UNKNOWN, conf=0.6, title=None, evidence=None):
    title = title or ("Software Engineer Intern" if etype == ET.INTERNSHIP else "Junior Software Engineer")
    o = Opportunity(title=title, company="X", apply_url=f"https://x/{title}", canonical_url=f"https://x/{title}",
                    employment_type=etype, status=Lifecycle.NEW, description="Build things with a friendly team.")
    o.eligibility = Eligibility(cat, conf, evidence or ["e"])
    o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
    return o


@pytest.mark.parametrize("etype,conf,expected", [
    (ET.INTERNSHIP, 0.6, None),
    (ET.NEW_GRAD, 0.6, None),                      # new: unverified new-grad is selected
    (ET.NEW_GRAD, 0.7, None),
    (ET.INTERNSHIP, 0.5, None),                    # unchanged
    (ET.NEW_GRAD, 0.5, "eligibility_unknown"),     # unchanged
    (ET.NEW_GRAD, 0.45, "eligibility_unknown"),
    (ET.NEW_GRAD, 0.3, "eligibility_unknown"),
])
def test_unverified_tier(etype, conf, expected):
    assert gate_reason(_opp(etype, conf=conf), 0.4) == expected


def test_unverified_goes_to_check_eligibility_never_apply():
    o = _opp(ET.NEW_GRAD)
    assert section_of(o) == CHECK_ELIGIBILITY


def test_positive_unchanged():
    assert gate_reason(_opp(ET.NEW_GRAD, EC.WORLDWIDE_REMOTE, 0.85), 0.4) is None


def test_marker_eligibility_line_in_check_section():
    o = Opportunity(title="Junior Software Engineer", company="X", apply_url="https://x/j", canonical_url="https://x/j",
                    ats_provider="himalayas", ats_job_id="https://himalayas.app/x/j", location_raw=_geo.NO_RESTRICTION_LISTED,
                    remote_status=RemoteStatus.REMOTE, employment_type=ET.NEW_GRAD, status=Lifecycle.NEW,
                    description="Build things with a friendly team.")
    o.eligibility = classify_eligibility(o, CFG.profile)
    o.relevance = score_opportunity(o, CFG.profile, ScoringConfig())
    assert gate_reason(o, 0.4) is None and section_of(o) == CHECK_ELIGIBILITY
    md = render_issue_md([o], CFG)
    assert "No location restriction listed on Himalayas or in the posting. Confirm before applying." in md
