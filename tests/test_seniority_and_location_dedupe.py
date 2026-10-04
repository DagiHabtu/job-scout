"""S4 — title-seniority hard filter, and fuzzy dedupe blocked by (company, location) (C7)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from job_scout.config import AppConfig
from job_scout.dedupe import dedupe
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import EmploymentType, Opportunity, Provenance
from job_scout.normalize import normalize
from job_scout.score import filter_reason

CFG = AppConfig()
CFG.profile.employment_types = [EmploymentType.INTERNSHIP, EmploymentType.STIPEND_PROGRAM, EmploymentType.NEW_GRAD]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _gh(job_id, location, description):
    return Opportunity(title="Software Engineer Intern", company="Globex", apply_url=f"https://gh/{job_id}",
                       canonical_url="", ats_provider="greenhouse", ats_job_id=job_id, location_raw=location,
                       description=description, provenance=[Provenance("greenhouse", f"https://gh/{job_id}", NOW)])


def test_c7_same_title_different_locations_stay_separate_and_emea_survives():
    us = _gh("1", "Remote, United States", "A long description of the US-based internship. " * 5)
    emea = _gh("2", "Remote, EMEA", "Short EMEA description.")
    out = dedupe([normalize(us), normalize(emea)])
    assert len(out) == 2
    cats = {o.location_raw: classify_eligibility(o, CFG.profile).category for o in out}
    assert cats["Remote, EMEA"] == EC.REMOTE_REGION_INCLUDES_USER
    assert cats["Remote, United States"] == EC.REMOTE_EXCLUDES_USER


def test_same_location_near_duplicate_still_merges():
    a = _gh("1", "Remote, EMEA", "short")
    b = _gh("2", "Remote, EMEA", "longer description")
    b.title = "Software Engineer Interns"
    assert len(dedupe([normalize(a), normalize(b)])) == 1


@pytest.mark.parametrize("title,etype,reason", [
    ("Senior Backend Engineer", EmploymentType.UNKNOWN, "seniority_title:senior"),
    ("Staff SRE", EmploymentType.UNKNOWN, "seniority_title:staff"),
    ("Engineering Manager, Platform", EmploymentType.NEW_GRAD, "seniority_title:manager"),
    ("Intern, Engineering Manager's Office", EmploymentType.INTERNSHIP, None),
    ("Backend Engineer", EmploymentType.UNKNOWN, None),          # no level signal: kept
])
def test_seniority_title_reason(title, etype, reason):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="u", employment_type=etype)
    assert filter_reason(o, CFG.profile, CFG.scoring, date(2026, 1, 1)) == reason


def test_type_check_precedes_seniority():
    o = Opportunity(title="Senior Engineer", company="X", apply_url="u", canonical_url="u",
                    employment_type=EmploymentType.CONTRACT)
    assert filter_reason(o, CFG.profile, CFG.scoring, date(2026, 1, 1)) == "type_unwanted:contract"
