"""Normalization — tracking-strip, honest remote inference, fingerprint, discovered_date stamp."""

from __future__ import annotations

from datetime import datetime, timezone

from job_scout.models import EmploymentType, Opportunity, RemoteStatus
from job_scout.normalize import (
    infer_employment_type,
    infer_remote_status,
    normalize,
    strip_tracking,
)


def _opp(**kw) -> Opportunity:
    base = dict(title="Backend Intern", company="Globex", apply_url="https://x/1", canonical_url="")
    base.update(kw)
    return Opportunity(**base)


def test_strip_tracking_removes_utm_but_keeps_meaningful_query():
    url = "https://jobs.example.com/apply?gh_jid=42&utm_source=news&utm_campaign=x&ref=twitter"
    out = strip_tracking(url)
    assert "gh_jid=42" in out            # a real job token is preserved
    assert "utm_" not in out and "ref=" not in out


def test_strip_tracking_is_stable_when_nothing_to_strip():
    url = "https://jobs.example.com/apply?gh_jid=42"
    assert strip_tracking(url) == url


def test_infer_remote_status_respects_explicit_value():
    # A source that already asserted a status is trusted; inference does not override it.
    assert infer_remote_status(_opp(remote_status=RemoteStatus.ONSITE, description="work from home")) == RemoteStatus.ONSITE


def test_infer_remote_status_from_text():
    assert infer_remote_status(_opp(description="This is a hybrid role.")) == RemoteStatus.HYBRID
    assert infer_remote_status(_opp(description="Fully remote, work from home.")) == RemoteStatus.REMOTE
    assert infer_remote_status(_opp(description="Strictly on-site in our office.")) == RemoteStatus.ONSITE


def test_infer_remote_status_stays_unknown_without_signal():
    assert infer_remote_status(_opp(description="Great team, great mission.")) == RemoteStatus.UNKNOWN


def test_normalize_sets_canonical_url_and_fingerprint_and_date():
    opp = _opp(apply_url="https://x/apply?utm_source=a", location_raw="Remote - EMEA")
    before = datetime.now(timezone.utc)
    out = normalize(opp)
    assert out.canonical_url == "https://x/apply"
    assert out.content_fingerprint  # non-empty, deterministic
    assert out.remote_status == RemoteStatus.REMOTE
    assert out.discovered_date is not None and out.discovered_date >= before


def test_normalize_does_not_overwrite_existing_discovered_date():
    stamped = datetime(2020, 1, 1, tzinfo=timezone.utc)
    out = normalize(_opp(discovered_date=stamped))
    assert out.discovered_date == stamped


def test_infer_employment_type_recognizes_internship_titles_from_unknown():
    # The Greenhouse case: adapter emits UNKNOWN; an explicit intern title must be recognized.
    for title in ("Software Engineering Intern", "Backend Internship - Summer 2027",
                  "Data Science Interns", "Co-op Software Developer", "Coop, Platform"):
        opp = _opp(title=title, employment_type=EmploymentType.UNKNOWN)
        assert infer_employment_type(opp) == EmploymentType.INTERNSHIP, title


def test_infer_employment_type_does_not_false_match_internal_or_international():
    # The trap: "Internal"/"International" must NOT be read as an internship. (GitLab's real board
    # has "Software Engineer (Internal Tooling)".)
    for title in ("Software Engineer (Internal Tooling)", "International Growth Manager",
                  "Senior Backend Engineer", "Staff SRE"):
        opp = _opp(title=title, employment_type=EmploymentType.UNKNOWN)
        assert infer_employment_type(opp) == EmploymentType.UNKNOWN, title


def test_infer_employment_type_never_overrides_a_source_value():
    # A structured source value (Lever/Ashby) is authoritative — inference must not touch it, even
    # if the title would otherwise suggest something else.
    opp = _opp(title="Engineering Intern", employment_type=EmploymentType.FULL_TIME)
    assert infer_employment_type(opp) == EmploymentType.FULL_TIME


import pytest  # noqa: E402

from job_scout.score import role_family_ok  # noqa: E402


@pytest.mark.parametrize("title,source_type,expected", [
    # intern tokens (UNKNOWN only)
    ("Werkstudent Data Engineering", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    ("Werkstudentin Software", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    ("Working Student - Backend", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    ("Software Trainee", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    ("DevOps Apprenticeship", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    ("Intern, Engineering Manager's Office", EmploymentType.UNKNOWN, EmploymentType.INTERNSHIP),
    # entry tokens (UNKNOWN or FULL_TIME, no seniority token)
    ("Junior Data Engineer", EmploymentType.UNKNOWN, EmploymentType.NEW_GRAD),
    ("Jr. Backend Developer", EmploymentType.FULL_TIME, EmploymentType.NEW_GRAD),
    ("Entry-Level Software Engineer", EmploymentType.FULL_TIME, EmploymentType.NEW_GRAD),
    ("New Grad Software Engineer", EmploymentType.UNKNOWN, EmploymentType.NEW_GRAD),
    ("Graduate Software Engineer", EmploymentType.UNKNOWN, EmploymentType.NEW_GRAD),
    ("Early Career Data Scientist", EmploymentType.UNKNOWN, EmploymentType.NEW_GRAD),
    ("Associate Software Engineer", EmploymentType.FULL_TIME, EmploymentType.NEW_GRAD),
    ("Associate Site Reliability Engineer", EmploymentType.UNKNOWN, EmploymentType.NEW_GRAD),
    # negatives
    ("Internal Tools Engineer", EmploymentType.UNKNOWN, EmploymentType.UNKNOWN),
    ("International Sales", EmploymentType.UNKNOWN, EmploymentType.UNKNOWN),
    ("Associate Renewals Manager", EmploymentType.UNKNOWN, EmploymentType.UNKNOWN),
    ("Junior Engineering Manager", EmploymentType.UNKNOWN, EmploymentType.UNKNOWN),   # seniority vetoes level
    ("Senior Software Engineer", EmploymentType.FULL_TIME, EmploymentType.FULL_TIME),
    ("Junior Contract Developer", EmploymentType.CONTRACT, EmploymentType.CONTRACT),  # only UNKNOWN/FULL_TIME refined
    ("Engineering Intern", EmploymentType.FULL_TIME, EmploymentType.FULL_TIME),      # intern token fills UNKNOWN only
])
def test_type_and_level_inference_table(title, source_type, expected):
    assert infer_employment_type(_opp(title=title, employment_type=source_type)) == expected


def test_graduate_marketing_manager_is_not_a_target():
    # Spec S3 lists this as "NEW_GRAD by level, vetoed by role family". With the spec's exact
    # regexes "manager" is a seniority token, so the level is not assigned at all; the role-family
    # veto (S5) also applies. Either way it can never be selected — both are asserted.
    t = "Graduate Partner Marketing Manager"
    assert infer_employment_type(_opp(title=t, employment_type=EmploymentType.UNKNOWN)) == EmploymentType.UNKNOWN
    assert role_family_ok(t) is False


def test_normalize_backfills_internship_type_end_to_end():
    out = normalize(_opp(title="Backend Engineering Intern", employment_type=EmploymentType.UNKNOWN))
    assert out.employment_type == EmploymentType.INTERNSHIP
