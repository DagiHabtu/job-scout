"""Acceptance 5.1 (spec 2026-10-21) — Appendix A regression: the 36 stored records behind Dagi's 35 labels,
reset to NEW and run through normalize → eligibility → hard filter → score → `gate_reason` (uncapped) →
`section_of` with today = 2026-10-21, land where §2 / Appendix A says. In-sample by construction."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from job_scout import _geo
from job_scout.config import AppConfig
from job_scout.eligibility import classify_eligibility
from job_scout.models import EmploymentType as ET, Lifecycle, Opportunity, RemoteStatus
from job_scout.normalize import normalize
from job_scout.notify import ACTIONABLE, ASPIRATIONAL, CHECK_ELIGIBILITY, OUTSIDE_INTERESTS, gate_reason, section_of
from job_scout.score import filter_reason, score_opportunity
from job_scout.sources.himalayas import _employment

ROOT = Path(__file__).resolve().parents[1]
CFG = AppConfig.load(str(ROOT / "config" / "profile.yaml"))
TODAY = date(2026, 10, 21)
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))

ANY_UNSELECTED = "any non-selection"
EXPECTED = {   # Appendix A "expected": a section, or the accepted reason code(s) for an unselected record
    "canon-kernel": ACTIONABLE, "canon-ubuntu": ACTIONABLE, "cloudcops": ACTIONABLE,
    "ritual-research": CHECK_ELIGIBILITY, "emetlab": CHECK_ELIGIBILITY, "avary": CHECK_ELIGIBILITY,
    "ritual-swe": CHECK_ELIGIBILITY, "gitlab-eoi": CHECK_ELIGIBILITY, "gitlab-sec": CHECK_ELIGIBILITY,
    "affidea-innov": CHECK_ELIGIBILITY, "affidea-devops": CHECK_ELIGIBILITY, "archwell": CHECK_ELIGIBILITY,
    "tether": ASPIRATIONAL,
    "vantum": OUTSIDE_INTERESTS, "makerble-test": OUTSIDE_INTERESTS, "crm": OUTSIDE_INTERESTS,
    "affidea-qa": OUTSIDE_INTERESTS, "resilio": OUTSIDE_INTERESTS,
    "tj-backend": {"eligibility:remote_excludes_user"}, "tj-frontend": {"eligibility:remote_excludes_user"},
    "micro1": {"role_family", "eligibility:remote_excludes_user"},
    "xp-swe": {"eligibility_unknown"}, "xp-ds": {"eligibility_unknown"},
    "xp-da": {"role_family"}, "xp-video": {"role_family"}, "c1-ta": {"role_family"}, "banco": {"role_family"},
    "holiday": {"pay:unpaid"}, "flowai": {"pay:unpaid"}, "makerble-devops": {"pay:unpaid"}, "bridges": {"pay:unpaid"},
    "ewor-dev": ANY_UNSELECTED, "ewor-cmo": ANY_UNSELECTED,
    "canon-grad": {"stage:graduate_only"}, "flowmingo": {"deadline_passed"},
}
PICKED = {"canon-kernel", "canon-ubuntu", "ritual-research", "emetlab", "avary", "vantum", "ritual-swe", "gitlab-eoi",
          "gitlab-sec", "cloudcops", "affidea-innov"}


def _fresh(d: dict) -> Opportunity:
    """The stored record as the current adapters would emit it, NEW."""
    himalayas = d.get("ats_provider") == "himalayas"
    etype = ET(d["employment_type"])
    if himalayas and etype == ET.INTERNSHIP:     # the old adapter typed every "Intern" as an internship (§4.7)
        etype = _employment({"employmentType": "Intern", "title": d["title"]})
    loc = d.get("location_raw")
    if himalayas and loc == "Worldwide":         # the old adapter's synthetic value for an empty restriction list
        loc = _geo.NO_RESTRICTION_LISTED
    return Opportunity(title=d["title"], company=d["company"], apply_url=d["apply_url"], canonical_url=d["canonical_url"],
                       ats_provider=d.get("ats_provider"), ats_job_id=d.get("ats_job_id"), location_raw=loc,
                       remote_status=RemoteStatus(d["remote_status"]), employment_type=etype,
                       description=d.get("description") or "", technologies=d.get("technologies") or [],
                       deadline=date.fromisoformat(d["deadline"][:10]) if d.get("deadline") else None,
                       salary_raw=d.get("salary_raw"), status=Lifecycle.NEW)


def _placement(d: dict) -> str:
    o = _fresh(d)
    normalize(o)
    o.eligibility = classify_eligibility(o, CFG.profile)
    reason = filter_reason(o, CFG.profile, CFG.scoring, TODAY)
    if reason:
        return reason
    o.relevance = score_opportunity(o, CFG.profile, CFG.scoring)
    return gate_reason(o, CFG.scoring.relevance_threshold) or section_of(o)


CASES = [(r["label_id"], r["key"], r["record"]) for r in _FX["records"]]


def test_fixture_covers_every_label():
    assert len(CASES) == 36 and {label for label, _, _ in CASES} == set(EXPECTED)


@pytest.mark.parametrize("label,key,record", CASES, ids=[f"{label}:{key[-30:]}" for label, key, _ in CASES])
def test_placement(label, key, record):
    got, want = _placement(record), EXPECTED[label]
    if isinstance(want, str) and want != ANY_UNSELECTED:
        assert got == want, (label, got)
    else:
        assert got not in (ACTIONABLE, CHECK_ELIGIBILITY, ASPIRATIONAL, OUTSIDE_INTERESTS), (label, got)
        if want != ANY_UNSELECTED:
            assert got in want, (label, got)


def test_no_picked_item_is_dropped():
    selected = {label for label, _, rec in CASES
                if _placement(rec) in (ACTIONABLE, CHECK_ELIGIBILITY, ASPIRATIONAL, OUTSIDE_INTERESTS)}
    assert PICKED <= selected
