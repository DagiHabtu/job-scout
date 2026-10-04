"""S2 — the LOCATION field decides first; body boilerplate is never positive evidence (C4)."""

from __future__ import annotations

import pytest

from job_scout.config import UserProfile
from job_scout.eligibility import BARE, ELSEWHERE, OTHER, USER, WORLD, _classify_location, classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import Opportunity, RemoteStatus

PROFILE = UserProfile()
BOILERPLATE = "GitLab is all-remote. Remote-Global benefits. Our EMEA sales team covers Europe, Middle East and Africa."


def _cls(location, title="Backend Engineer", body=BOILERPLATE, remote=RemoteStatus.REMOTE):
    o = Opportunity(title=title, company="X", apply_url="https://x/1", canonical_url="", location_raw=location,
                    description=body, remote_status=remote)
    return classify_eligibility(o, PROFILE)


@pytest.mark.parametrize("location,title,body,expected,conf", [
    # spec S2 table
    ("Bangalore, India", "Backend Engineer", BOILERPLATE, {EC.ONSITE_FOREIGN, EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote, France", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote, EMEA", "Backend Engineer", BOILERPLATE, {EC.REMOTE_REGION_INCLUDES_USER}, 0.8),
    ("Remote, Germany; Remote, EMEA", "Backend Engineer", BOILERPLATE, {EC.REMOTE_REGION_INCLUDES_USER}, 0.8),
    ("Remote", "Backend Engineer, US [IC5]", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote", "Backend Engineer", "You can work from anywhere.", {EC.WORLDWIDE_REMOTE}, 0.7),
    ("Remote", "Backend Engineer", "We build developer tools.", {EC.UNKNOWN}, 0.5),
    ("Addis Ababa, Ethiopia", "Backend Engineer", BOILERPLATE, {EC.REMOTE_REGION_INCLUDES_USER}, 0.8),
    # C4 reproductions on the other stored locations
    ("Remote, Germany", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote, Singapore", "Enterprise Account Executive - Singapore", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote Ireland", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote, KSA; Remote, UAE", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("San Francisco, CA", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote (EMEA)", "Backend Engineer", BOILERPLATE, {EC.REMOTE_REGION_INCLUDES_USER}, 0.8),
    ("Remote, North America", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    ("Remote, Kenya", "Backend Engineer", BOILERPLATE, {EC.REMOTE_EXCLUDES_USER}, 0.85),
    # worldwide in the location field
    ("Worldwide", "Backend Engineer", "", {EC.WORLDWIDE_REMOTE}, 0.85),
    ("Remote - Global", "Backend Engineer", "", {EC.WORLDWIDE_REMOTE}, 0.85),
    # a worldwide word qualified by a named place in the same segment is a restriction
    ("Remote - Anywhere in the US", "Backend Engineer", "", {EC.REMOTE_EXCLUDES_USER}, 0.85),
    # bare "Remote" and boilerplate body: not positive ("global"/"emea" in the body no longer count)
    ("Remote", "Backend Engineer", BOILERPLATE, {EC.UNKNOWN}, 0.5),
])
def test_location_decides(location, title, body, expected, conf):
    e = _cls(location, title, body)
    assert e.category in expected, e.evidence
    assert e.confidence == pytest.approx(conf)
    assert e.evidence


def test_non_remote_elsewhere_is_onsite_foreign():
    e = _cls("Hybrid (UK)", body="Hybrid role.", remote=RemoteStatus.HYBRID)
    assert e.category == EC.ONSITE_FOREIGN and e.confidence == pytest.approx(0.8)
    e = _cls("Bangalore, India", body="Office role.", remote=RemoteStatus.UNKNOWN)
    assert e.category == EC.ONSITE_FOREIGN


def test_body_cannot_rescue_a_named_elsewhere_location():
    e = _cls("Remote, France", body="We hire anywhere in the world. Work from anywhere. Africa and EMEA welcome.")
    assert e.category == EC.REMOTE_EXCLUDES_USER


def test_onsite_in_own_city_stays_unknown_per_gate0_decision():
    e = _cls("Addis Ababa, Ethiopia", remote=RemoteStatus.ONSITE, body="Onsite in our Addis office.")
    assert e.category == EC.UNKNOWN and e.confidence == pytest.approx(0.4)


def test_no_location_neutral_body_is_unknown_low():
    e = _cls(None, body="We build developer tools.")
    assert e.category == EC.UNKNOWN and e.confidence == pytest.approx(0.3)


def test_user_country_code_in_location_is_user():
    assert _classify_location("Remote, ET", "Engineer", PROFILE)[0] == USER


@pytest.mark.parametrize("location,label", [
    ("Remote", BARE),
    ("Remote, Canada; Remote, United States", ELSEWHERE),
    ("Remote; Remote, Canada; Remote, United States", BARE),   # a bare segment keeps it undecided
    ("Remote, Mid-Market", OTHER),
    ("Remote - US, UK, EMEA", USER),
    ("International", WORLD),
])
def test_classify_location_labels(location, label):
    assert _classify_location(location, "Engineer", PROFILE)[0] == label


def test_classify_location_none_without_location_or_marker():
    assert _classify_location(None, "Engineer", PROFILE) is None
    assert _classify_location(None, "Account Executive - Singapore", PROFILE)[0] == ELSEWHERE
