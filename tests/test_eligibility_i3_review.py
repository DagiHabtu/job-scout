"""Iteration 3 — fresh-context review of 4.1+4.2 (2026-10-21). Each finding is a test, written before any fix.

Location is the aggregator marker unless a test says otherwise; a body that does not require a place
elsewhere must not be dropped (UNKNOWN 0.6 = "Check eligibility").
"""

from __future__ import annotations

import pytest

from job_scout import _geo
from job_scout.config import UserProfile
from job_scout.eligibility import classify_eligibility
from job_scout.models import DISQUALIFYING_ELIGIBILITY, EligibilityCategory as EC, EmploymentType as ET, Opportunity, RemoteStatus

MARKER = _geo.NO_RESTRICTION_LISTED
PROFILE = UserProfile()


def _elig(body, loc=MARKER):
    o = Opportunity(title="Software Engineer Intern", company="X", apply_url="u", canonical_url="u", location_raw=loc,
                    remote_status=RemoteStatus.REMOTE, employment_type=ET.INTERNSHIP, description=body)
    return classify_eligibility(o, PROFILE)


@pytest.mark.parametrize("body", [
    # H1 — negated, conditional and descriptive "based/located/living in X"
    "You do not need to be based in the US to apply.",
    "You don't have to be located in Europe.",
    "You are not required to be based in the US.",
    "If you're based in Europe, great. We hire everywhere.",
    "Whether you are based in Europe or Asia, you are welcome.",
    "Most engineers are based in Europe. We hire everywhere.",
    "Engineers based in Lagos, Nairobi and Berlin collaborate daily.",
    "Founded in 2015 and based in Berlin, Acme builds tools.",
    "HQ located in Austin, Texas.",
    "Headquarters located in New York.",
    "The high cost of living in London is not a concern for remote staff.",
    # H2 — "<place>-based" describing the employer, its customers, or working hours
    "Acme is London-based but hires globally.",
    "We serve US-based and European customers.",
    "Work US-based hours (EST).",
])
def test_not_a_requirement(body):
    e = _elig(body)
    assert e.category not in DISQUALIFYING_ELIGIBILITY, e.evidence


@pytest.mark.parametrize("body", [
    # M1 — "a US-based engineer" is the hire, not the employer: a requirement, not silence
    "We are looking for a US-based engineer to join us.",
    "We're hiring an EU-based developer.",
])
def test_article_before_a_person_noun_is_a_requirement(body):
    e = _elig(body)
    assert (e.category, e.confidence) == (EC.REMOTE_EXCLUDES_USER, 0.75), e.evidence


@pytest.mark.parametrize("body", [
    # M2 — a benefits "bonus" in an earlier sentence is not a preference for a later requirement
    "Perks: performance bonus and laptop. Location: Remote (US only)",
    "Perks: performance bonus. You should be located in the United States.",
])
def test_preference_window_stops_at_a_sentence_end(body):
    e = _elig(body)
    assert (e.category, e.confidence) == (EC.REMOTE_EXCLUDES_USER, 0.75), e.evidence


def test_new_shapes_do_not_run_for_an_unrecognised_location_field():
    # M3 — §3: the §4.1 body rules apply only to an absent, bare "Remote" or marker location
    e = _elig("Most engineers are based in Europe.", loc="Flexible")
    assert not any("requires a location outside" in x for x in e.evidence), e.evidence


def test_middle_east_and_africa_confidence():
    # test weakness — the spec-table row asserted no confidence
    e = _elig("Remote (Middle East and Africa)")
    assert (e.category, e.confidence) == (EC.REMOTE_REGION_INCLUDES_USER, 0.7), e.evidence


@pytest.mark.parametrize("body", [
    # guards: the real requirements still exclude
    "You should be located in the United States.",
    "Candidates must reside in Canada.",
    "We are hiring US-based candidates only.",
])
def test_real_requirements_still_exclude(body):
    assert _elig(body).category in DISQUALIFYING_ELIGIBILITY
