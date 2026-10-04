"""S2 independent-review findings, each as a test (spec §11: finding → test → fix or refute)."""

from __future__ import annotations

import pytest

from job_scout.config import UserProfile
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import Opportunity, RemoteStatus

P = UserProfile()
EXCLUDED = {EC.REMOTE_EXCLUDES_USER, EC.ONSITE_FOREIGN}


def _c(location, body="", remote=RemoteStatus.REMOTE, title="Backend Engineer"):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="", location_raw=location,
                    description=body, remote_status=remote)
    return classify_eligibility(o, P)


# H1 — "africa" inside another country/region name is not the user's region
@pytest.mark.parametrize("loc,remote", [
    ("Remote, South Africa", RemoteStatus.REMOTE),
    ("Johannesburg, South Africa", RemoteStatus.ONSITE),
    ("Remote - North Africa", RemoteStatus.REMOTE),
    ("Remote, West Africa", RemoteStatus.REMOTE),
])
def test_h1_other_african_places_are_excluded(loc, remote):
    assert _c(loc, remote=remote).category in EXCLUDED


# H2 — an onsite role in a foreign city is not reachable because the segment names a region
@pytest.mark.parametrize("loc", ["Nairobi, Kenya (East Africa)", "London, UK (EMEA HQ)"])
def test_h2_onsite_foreign_with_regional_token(loc):
    assert _c(loc, remote=RemoteStatus.ONSITE).category == EC.ONSITE_FOREIGN


# H3 — "ET" as a time zone is not Ethiopia
@pytest.mark.parametrize("loc", ["Remote, US (ET)", "New York, NY - ET hours"])
def test_h3_eastern_time_is_not_ethiopia(loc):
    assert _c(loc).category in EXCLUDED


# H4 / M2 — a worldwide phrase qualified by a named place is not worldwide
@pytest.mark.parametrize("body", [
    "You can work from anywhere within the US.",
    "Remote role, US only. You can work from anywhere you like in the US.",
    "Hire in any country we have an entity in (US, UK).",
])
def test_h4_qualified_worldwide_phrase_is_not_positive(body):
    assert _c("Remote", body).category not in {EC.WORLDWIDE_REMOTE, EC.REMOTE_REGION_INCLUDES_USER}


def test_h4_us_hours_stays_a_penalty_not_a_restriction():
    e = _c("Remote", "Fully remote worldwide, but you must overlap with US business hours.")
    assert e.category == EC.WORLDWIDE_REMOTE and e.confidence == pytest.approx(0.5)


# M1 / M2 — a location naming elsewhere places is never made worldwide or excluded by body words
@pytest.mark.parametrize("body", ["We build tools.", "Remote-Global benefits.", "All-remote; work from anywhere."])
def test_m1_mixed_bare_and_elsewhere_is_unknown_regardless_of_body(body):
    e = _c("Remote; Remote, Canada; Remote, United States", body)
    assert e.category == EC.UNKNOWN and e.confidence == pytest.approx(0.5)


@pytest.mark.parametrize("loc", ["Remote, California", "Remote, Germany; Remote, Cologne"])
def test_m2_elsewhere_location_never_rescued_by_body(loc):
    assert _c(loc, "All-remote; work from anywhere.").category not in {EC.WORLDWIDE_REMOTE, EC.REMOTE_REGION_INCLUDES_USER}


# M3 — multi-word country names containing "and" survive segment splitting
@pytest.mark.parametrize("loc", ["Remote, Bosnia and Herzegovina", "Remote, Trinidad and Tobago"])
def test_m3_and_inside_country_names(loc):
    assert _c(loc).category == EC.REMOTE_EXCLUDES_USER


def test_m3_middle_east_and_africa_still_includes():
    assert _c("Remote, Middle East and Africa").category == EC.REMOTE_REGION_INCLUDES_USER


# M4 — an explicit "<elsewhere> only" qualifier narrows a broad region
def test_m4_europe_only_qualifier_excludes():
    assert _c("Remote - EMEA (Europe only)").category in EXCLUDED


def test_m4_unqualified_multi_region_still_includes():
    assert _c("Remote - US, UK, EMEA").category == EC.REMOTE_REGION_INCLUDES_USER


# L2 — onsite in the user's own city, detected from the body when the status is unset
def test_l2_onsite_own_city_from_body_is_unknown_04():
    e = _c("Addis Ababa, Ethiopia", "On-site in our Addis office.", remote=RemoteStatus.UNKNOWN)
    assert e.category == EC.UNKNOWN and e.confidence == pytest.approx(0.4)
