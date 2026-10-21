"""Iteration 3 §4.1 — honest eligibility for aggregator listings. Written before the code.

Himalayas writes `_geo.NO_RESTRICTION_LISTED` for an empty `locationRestrictions` (it used to write
"Worldwide", which outranked what the employer wrote). Bodies named by label_id are the stored texts
(tests/fixtures/labels_2026-10-21_records.json).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout import _geo
from job_scout.config import UserProfile
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC, EmploymentType as ET, Opportunity, RemoteStatus
from job_scout.sources.himalayas import _to_opportunity

ROOT = Path(__file__).resolve().parents[1]
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))
BODY = {r["label_id"]: r["record"]["description"] for r in _FX["records"]}
MARKER = _geo.NO_RESTRICTION_LISTED
PROFILE = UserProfile()


def _elig(loc, body, title="Software Engineer Intern"):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="u", location_raw=loc,
                    remote_status=RemoteStatus.REMOTE, employment_type=ET.INTERNSHIP, description=body)
    return classify_eligibility(o, PROFILE)


def test_marker_value():
    assert MARKER == "Remote (no location restriction listed)"


def test_adapter_writes_marker_for_empty_restrictions():
    o = _to_opportunity({"title": "Software Engineer Intern", "guid": "https://himalayas.app/x/1",
                         "locationRestrictions": [], "employmentType": "Intern"})
    assert o.location_raw == MARKER
    o = _to_opportunity({"title": "Software Engineer Intern", "guid": "https://himalayas.app/x/2",
                         "locationRestrictions": ["Germany", "France"], "employmentType": "Intern"})
    assert o.location_raw == "Germany; France"


@pytest.mark.parametrize("loc,body,category,confidence", [
    (MARKER, BODY["tj-backend"], EC.REMOTE_EXCLUDES_USER, 0.75),
    (MARKER, BODY["tj-frontend"], EC.REMOTE_EXCLUDES_USER, 0.75),
    (MARKER, BODY["micro1"], EC.REMOTE_EXCLUDES_USER, 0.75),
    (MARKER, "We are a US-based company. Work from anywhere.", EC.WORLDWIDE_REMOTE, 0.7),
    (MARKER, BODY["xp-swe"], EC.UNKNOWN, 0.45),
    (MARKER, BODY["xp-ds"], EC.UNKNOWN, 0.45),
    (MARKER, BODY["ewor-dev"], EC.UNKNOWN, 0.5),
    (MARKER, BODY["cloudcops"], EC.WORLDWIDE_REMOTE, 0.7),
    (MARKER, BODY["bridges"], EC.WORLDWIDE_REMOTE, 0.7),
    (MARKER, BODY["ritual-swe"], EC.UNKNOWN, 0.6),
    (MARKER, "Remote (Middle East and Africa)", EC.REMOTE_REGION_INCLUDES_USER, None),
    # employer field authoritative (Decision #6) — recorded in STATE as an accepted case
    ("Home based - Worldwide", "We are hiring only US-based candidates", EC.WORLDWIDE_REMOTE, None),
])
def test_spec_table(loc, body, category, confidence):
    e = _elig(loc, body)
    assert e.category == category, e.evidence
    if confidence is not None:
        assert e.confidence == confidence, e.evidence


def test_unstated_evidence_names_the_marker():
    e = _elig(MARKER, BODY["ritual-swe"])
    assert "Himalayas lists no location restriction; the posting states none" in e.evidence


def test_preference_evidence_quotes_the_sentence():
    e = _elig(MARKER, BODY["xp-swe"])
    assert any(x.startswith("states a location preference: '") and "English-speaking country" in x
               for x in e.evidence), e.evidence


def test_relocation_sentence_is_evidence():
    e = _elig(MARKER, BODY["ewor-dev"])
    assert any("open to relocate" in x for x in e.evidence), e.evidence


def test_required_exclusion_is_at_the_disqualify_threshold():
    e = _elig(MARKER, BODY["micro1"])
    assert e.is_confident_disqualifier(0.75)


@pytest.mark.parametrize("body,category,confidence", [
    # (d) no evidence: 0.6 marker, 0.5 bare "Remote", 0.3 no location
    ("Build things with a friendly team.", EC.UNKNOWN, 0.6),
    # region list in the body, every item elsewhere
    ("Remote (Europe; Middle East; North America).", EC.REMOTE_EXCLUDES_USER, 0.75),
    ("Remote (Global). Build things.", EC.WORLDWIDE_REMOTE, 0.7),
    ("You should be located in the United States.", EC.REMOTE_EXCLUDES_USER, 0.75),
    ("Candidates should be living in Canada.", EC.REMOTE_EXCLUDES_USER, 0.75),
    ("You are based in Ethiopia or Kenya.", EC.UNKNOWN, 0.6),            # names the user: not an exclusion
    ("We are a startup based in Portugal. Build things.", EC.UNKNOWN, 0.6),   # company location, not a requirement
    ("Our team is based in Berlin.", EC.UNKNOWN, 0.6),
    ("A plus: based in Europe.", EC.UNKNOWN, 0.45),
    ("Being based in Europe is a plus.", EC.UNKNOWN, 0.45),             # deviation i3-b
    ("You are based in Europe. Benefits: a plus for everyone.", EC.REMOTE_EXCLUDES_USER, 0.75),
    ("Nice to have: EU-based.", EC.UNKNOWN, 0.45),
    ("There are no geographic restrictions.", EC.WORLDWIDE_REMOTE, 0.7),
    ("Living in a rural or smaller community.", EC.UNKNOWN, 0.6),        # not a place
    ("Remote (Relocation to Portugal Available).", EC.UNKNOWN, 0.6),     # a relocation option, not a restriction
])
def test_marker_body_rules(body, category, confidence):
    e = _elig(MARKER, body)
    assert (e.category, e.confidence) == (category, confidence), e.evidence


@pytest.mark.parametrize("body", [
    # stored Himalayas bodies (2026-10-21 probe) that describe employers, not where the hire must be — i3-c
    "We connect you with rewarding, remote job opportunities with US-based employers who recognize your skills.",
    "TCCA connects skilled professionals with remote opportunities supporting U.S.-based companies across technology.",
    "Based in Melbourne, Australia, we are growing our technology team.",
    "If you're NOT based in the Philippines, please apply here.",
    # the old coarse body rule is not applied to the marker — i3-d (Affidea DevOps: 'apac' inside "capacity")
    "0-2 years' experience in a devops, systems administration, or software development support capacity.",
    "We are recruiting for roles outside the U.S., and candidates can anticipate 10-35 hours of work per week.",
    "You write natural, conversational US English, and you can show us.",
])
def test_marker_body_false_exclusions(body):
    e = _elig(MARKER, body)
    assert (e.category, e.confidence) == (EC.UNKNOWN, 0.6), e.evidence


@pytest.mark.parametrize("body,category,confidence", [
    # stored Greenhouse bodies, location "Remote" (2026-10-21 old-vs-new probe over all 380 rows)
    ("While we hire almost anywhere in the world, we have a preference for someone to reside in the United "
     "States for this role.", EC.UNKNOWN, 0.45),
    # alone, these two still trip the unchanged coarse rule ("north america" / "u.s." with no guard word) → 0.8
    # as before; the stored bodies carry a guard word. The point: the new shapes do not fire.
    ("Because this role will work closely with leaders in Eastern Time and with customers primarily located in "
     "North America, you must have substantial working-hour overlap.", EC.REMOTE_EXCLUDES_USER, 0.8),
    ("Remote-Global The base salary range for this role's listed level is currently for residents of the United "
     "States only.", EC.UNKNOWN, 0.5),
    ("For U.S. based applicants only, the starting pay range for this position is generally within this range.",
     EC.REMOTE_EXCLUDES_USER, 0.8),
])
def test_bare_remote_body_false_exclusions(body, category, confidence):
    e = _elig("Remote", body)
    assert (e.category, e.confidence) == (category, confidence), e.evidence
    assert not any("requires a location outside" in x for x in e.evidence)


def test_affidea_devops_is_check_eligibility_material():
    e = _elig(MARKER, BODY["affidea-devops"], title="Junior DevOps Engineer")
    assert (e.category, e.confidence) == (EC.UNKNOWN, 0.6), e.evidence


def test_bare_remote_keeps_the_coarse_body_rule():
    # unchanged for a bare "Remote" location (only the marker skips it)
    assert _elig("Remote", "Open to candidates in Canada.").category == EC.REMOTE_EXCLUDES_USER


def test_bare_and_absent_confidences():
    assert (_elig("Remote", "Build things.").category, _elig("Remote", "Build things.").confidence) == (EC.UNKNOWN, 0.5)
    e = _elig(None, "Build things.")
    assert (e.category, e.confidence) == (EC.UNKNOWN, 0.3)
    e = _elig("Remote", "You must be based in the UK.")
    assert e.category in (EC.REMOTE_EXCLUDES_USER, EC.REQUIRES_WORK_AUTH)


def test_marker_with_title_region_is_excluded():
    # an ELSEWHERE title marker qualifies the marker as it qualifies a bare "Remote"
    e = _elig(MARKER, "Build things.", title="Software Engineer Intern (US)")
    assert e.category == EC.REMOTE_EXCLUDES_USER


def test_geo_additions():
    assert "english-speaking country" in _geo.REGIONS_EXCLUDING_AFRICA
    assert "english speaking country" in _geo.REGIONS_EXCLUDING_AFRICA
    assert "middle east" in _geo.REGIONS_EXCLUDING_AFRICA
    assert "middle east and africa" in _geo.REGIONS_INCLUDING_AFRICA
