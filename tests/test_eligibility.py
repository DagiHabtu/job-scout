"""Eligibility classifier — one assertion per category, plus the confidence/penalty behaviour.

The classifier is deliberately conservative (favours UNKNOWN over a wrong confident call), so these
tests pin BOTH the category and the confidence band that gates hard-filtering.
"""

from __future__ import annotations

from job_scout.config import UserProfile
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import EmploymentType, Opportunity, RemoteStatus


def _opp(**kw) -> Opportunity:
    base = dict(title="Intern", company="X", apply_url="https://x/1", canonical_url="")
    base.update(kw)
    return Opportunity(**base)


PROFILE = UserProfile()  # ET-resident, authorized only in ET — the configured default


def test_stipend_program_is_globally_eligible(monkeypatch):
    # Updated (S2): a curated program round is eligible only on its program's own verified rule
    # (geo_verdict), not because it is a stipend program.
    import job_scout.sources.known_programs as kp

    monkeypatch.setattr(kp, "geo_verdict", lambda job_id, country: "eligible")
    e = classify_eligibility(_opp(employment_type=EmploymentType.STIPEND_PROGRAM, ats_provider="known_programs",
                                  ats_job_id="x@open", description="Outreachy paid open source internship."), PROFILE)
    assert e.category == EC.STIPEND_PROGRAM_GLOBAL
    assert e.confidence >= 0.85


def test_stipend_program_from_another_source_uses_location_rules():
    # Updated (S2): "stipend ⇒ worldwide" is no longer assumed outside the curated table.
    e = classify_eligibility(_opp(employment_type=EmploymentType.STIPEND_PROGRAM,
                                  description="Outreachy paid open source internship."), PROFILE)
    assert e.category == EC.UNKNOWN


def test_program_name_in_text_is_not_a_program_round():
    # Inverted (S2): a posting that mentions GSoC is not a GSoC round — the same boilerplate defect as C4.
    e = classify_eligibility(_opp(description="Apply to Google Summer of Code (GSoC) this year."), PROFILE)
    assert e.category == EC.UNKNOWN and e.confidence == 0.3      # pinned (S2 review)


def test_requires_work_auth_is_a_confident_disqualifier():
    e = classify_eligibility(_opp(description="Must be a US citizen with an active security clearance."), PROFILE)
    assert e.category in {EC.REQUIRES_WORK_AUTH, EC.REMOTE_EXCLUDES_USER}  # either way, disqualifying
    assert e.confidence >= 0.75


def test_work_auth_not_masked_by_country_code_substring():
    # Regression: "et" must not match inside 'meetings' and mask a real foreign-auth requirement.
    e = classify_eligibility(
        _opp(description="Applicants must have the right to work in Germany. Weekly team meetings."),
        PROFILE,
    )
    assert e.category == EC.REQUIRES_WORK_AUTH
    assert e.confidence >= 0.75


def test_benign_country_of_residence_is_not_a_disqualifier():
    # GSoC-style phrasing: eligible to work in YOUR OWN country is not a foreign-auth requirement.
    e = classify_eligibility(_opp(description="You must be authorized to work in your country of residence."), PROFILE)
    assert e.category != EC.REQUIRES_WORK_AUTH


def test_requires_auth_in_own_country_is_not_disqualifying():
    e = classify_eligibility(_opp(description="Must be authorized to work in Ethiopia."), PROFILE)
    assert e.category != EC.REQUIRES_WORK_AUTH


def test_remote_excludes_user_when_region_restricted():
    e = classify_eligibility(_opp(description="Remote role, US only.", location_raw="Remote (US only)"), PROFILE)
    assert e.category == EC.REMOTE_EXCLUDES_USER
    assert e.confidence >= 0.75


def test_explicit_excluding_location_beats_worldwide_boilerplate():
    # Regression (live-found): an all-remote employer's generic "global / work from anywhere"
    # description must NOT rescue a role whose LOCATION field is explicitly Canada/US.
    e = classify_eligibility(
        _opp(
            title="Backend Engineer",
            location_raw="Remote, Canada; Remote, United States",
            description="We are the world's largest all-remote company — work from anywhere, global team. Build in Python.",
        ),
        PROFILE,
    )
    assert e.category == EC.REMOTE_EXCLUDES_USER
    assert e.confidence >= 0.75


def test_multiregion_location_including_user_is_kept():
    # The same authority cuts both ways: a location that also names EMEA is NOT excluded.
    e = classify_eligibility(
        _opp(title="Backend Engineer", location_raw="Remote - US, UK, EMEA",
             description="Global all-remote team."),
        PROFILE,
    )
    assert e.category != EC.REMOTE_EXCLUDES_USER


def test_onsite_foreign_is_disqualifying():
    e = classify_eligibility(
        _opp(remote_status=RemoteStatus.ONSITE, location_raw="Berlin, Germany",
             description="Onsite role based in our Berlin office."),
        PROFILE,
    )
    assert e.category == EC.ONSITE_FOREIGN
    assert e.confidence >= 0.75


def test_onsite_in_own_country_is_unknown_not_dropped():
    # The category-gap case (STATE decision): eligible but not remote → honest UNKNOWN, low conf.
    e = classify_eligibility(
        _opp(remote_status=RemoteStatus.ONSITE, location_raw="Addis Ababa, Ethiopia",
             description="Onsite role in Addis Ababa."),
        PROFILE,
    )
    assert e.category == EC.UNKNOWN
    assert e.confidence < 0.75  # never disqualifying, never confidently positive


def test_remote_region_includes_user():
    e = classify_eligibility(_opp(description="Remote across EMEA.", location_raw="Remote - EMEA"), PROFILE)
    assert e.category == EC.REMOTE_REGION_INCLUDES_USER


def test_worldwide_remote():
    e = classify_eligibility(_opp(description="Fully remote worldwide — work from anywhere."), PROFILE)
    assert e.category == EC.WORLDWIDE_REMOTE
    assert e.confidence >= 0.7


def test_unknown_when_no_signal():
    e = classify_eligibility(_opp(description="Join our team building web services in Python."), PROFILE)
    assert e.category == EC.UNKNOWN
    assert e.confidence <= 0.5


def test_us_hours_requirement_penalizes_worldwide_confidence():
    strong = classify_eligibility(_opp(description="Fully remote worldwide, work from anywhere."), PROFILE)
    penalized = classify_eligibility(
        _opp(description="Fully remote worldwide, but you must overlap with US business hours."), PROFILE
    )
    assert penalized.category == EC.WORLDWIDE_REMOTE
    assert penalized.confidence < strong.confidence
    assert any("us-hours" in x.lower() or "us business" in x.lower() or "utc+3" in x.lower()
               for x in penalized.evidence)


def test_every_result_carries_evidence():
    for desc in ["Outreachy internship", "Must be a US citizen", "Remote across EMEA", "Nothing specific here"]:
        e = classify_eligibility(_opp(description=desc), PROFILE)
        assert e.evidence, f"no evidence recorded for {desc!r}"
