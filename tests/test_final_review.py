"""Final whole-branch review findings, each as a test (spec §11: finding → test → fix or refute)."""

from __future__ import annotations

import pytest

from job_scout.config import UserProfile
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import Opportunity, RemoteStatus

P = UserProfile()
EXCLUDED = {EC.REMOTE_EXCLUDES_USER, EC.ONSITE_FOREIGN}


def _c(location, body="", remote=RemoteStatus.REMOTE, title="Software Engineer Intern"):
    o = Opportunity(title=title, company="X", apply_url="u", canonical_url="", location_raw=location,
                    description=body, remote_status=remote)
    return classify_eligibility(o, P)


# H1 — the pronoun "us" is not the United States.
def test_h1_pronoun_us_is_not_a_region():
    e = _c("Remote", "Come build our data platform with us. Tell us about yourself.")
    assert e.category == EC.UNKNOWN and e.confidence == 0.5


def test_h1_country_us_still_restricts():
    assert _c("Remote", "This role is open to candidates in the US.").category == EC.REMOTE_EXCLUDES_USER


# H2 — a worldwide phrase followed later by an explicit residency requirement elsewhere is not worldwide.
SOURCEGRAPH = ("While we hire almost anywhere in the world, we do require successful candidates to be "
               "located in the United States for this role.")


def test_h2_residency_requirement_cancels_worldwide_phrase():
    e = _c("Remote", SOURCEGRAPH)
    assert e.category == EC.UNKNOWN and e.confidence == 0.5


def test_h2_worldwide_phrase_alone_still_worldwide():
    assert _c("Remote", "We hire almost anywhere in the world.").category == EC.WORLDWIDE_REMOTE


def test_h2_residency_in_users_region_does_not_cancel():
    body = ("Work from anywhere. We are a small, fully distributed team building developer tools. "
            "Several teammates are located in Africa.")
    assert _c("Remote", body).category == EC.WORLDWIDE_REMOTE


# M1 — a visa-sponsorship line does not override a decisive worldwide / user-region location.
def test_m1_no_sponsorship_with_worldwide_location():
    assert _c("Worldwide", "Fully remote. We do not sponsor visas.").category == EC.WORLDWIDE_REMOTE


def test_m1_based_in_users_region():
    assert _c("Remote, EMEA", "Candidates must be based in EMEA.").category == EC.REMOTE_REGION_INCLUDES_USER


def test_m1_foreign_right_to_work_still_disqualifies():
    e = _c("Remote, EMEA", "You must have the right to work in the UK.")
    assert e.category == EC.REQUIRES_WORK_AUTH


def test_m1_sponsorship_still_disqualifies_without_decisive_location():
    assert _c("Remote", "We will not sponsor visas.").category == EC.REQUIRES_WORK_AUTH


# M2 / L10 — exclusion wording in the location field.
@pytest.mark.parametrize("loc,remote", [
    ("Remote - Global (excluding US)", RemoteStatus.REMOTE),
    ("Anywhere except the United States", RemoteStatus.UNKNOWN),
])
def test_m2_global_except_elsewhere_is_worldwide(loc, remote):
    assert _c(loc, remote=remote).category == EC.WORLDWIDE_REMOTE


def test_l10_region_excluding_user_is_excluded():
    assert _c("Remote - EMEA, excluding Ethiopia").category == EC.REMOTE_EXCLUDES_USER


def test_l10_fully_remote_is_bare():
    e = _c("Fully Remote")
    assert e.category == EC.UNKNOWN and e.confidence == 0.5


# M3 — common sub-national places are recognised, so body boilerplate cannot decide.
@pytest.mark.parametrize("loc", ["Remote, Ontario", "Remote - British Columbia", "Remote, Karnataka",
                                 "Remote, Bay Area", "Remote, New South Wales"])
def test_m3_subnational_places_are_elsewhere(loc):
    assert _c(loc, "You can work from anywhere.").category in EXCLUDED


# L9 — a worldwide location (often synthetic, e.g. Himalayas' empty restrictions) next to an
# elsewhere title marker is mixed → UNKNOWN, not confidently worldwide.
def test_l9_world_location_with_elsewhere_title_marker_is_unknown():
    assert _c("Worldwide", title="Software Engineer Intern (US)").category == EC.UNKNOWN


# H3 — fuzzy dedupe never merges across levels.
def test_h3_junior_and_senior_are_not_merged():
    from job_scout.dedupe import dedupe

    def gh(i, title, body):
        return Opportunity(title=title, company="Sourcegraph", apply_url=f"u{i}", canonical_url=f"u{i}",
                           ats_provider="greenhouse", ats_job_id=str(i), location_raw="Remote, EMEA",
                           description=body)

    out = dedupe([gh(1, "Junior Data Engineer", "short"), gh(2, "Senior Data Engineer", "a much longer description")])
    assert sorted(o.title for o in out) == ["Junior Data Engineer", "Senior Data Engineer"]


# M4 — a team-name suffix does not veto a technical title; a non-technical trainee is still vetoed.
@pytest.mark.parametrize("title,ok", [
    ("Software Engineer Intern, Financial Data Platform", True),
    ("Data Engineer Intern - Policy Platform", True),
    ("Machine Learning Engineer Intern - Content Understanding", True),
    ("Backend Engineer Intern, People Platform", True),
    ("Software Engineer Intern, Developer Support Tools", True),
    ("Data Scientist Intern - Sales Analytics", True),
    ("Security Guard Trainee", False),
    ("Sales Engineer Intern", False),
    ("Intern, Engineering Manager's Office", False),
    ("Business Development & Strategy Intern (MBA) - Nearby.ai", False),
])
def test_m4_role_family_head(title, ok):
    from job_scout.score import role_family_ok

    assert role_family_ok(title) is ok


# M5 — skipped records are counted per source, so an all-skipped source is not a silent zero.
def test_m5_skipped_records_are_reported(tmp_path):
    from job_scout.config import AppConfig, SourceConfig
    from job_scout.pipeline import run_once
    from job_scout.sources.greenhouse import GreenhouseSource

    src = GreenhouseSource(["b"], fetch_json=lambda url: {"jobs": [{"id": 1}, {"id": 2}]} if "/jobs" in url else {})
    assert src.fetch(SourceConfig()) == [] and src.skipped_records == 2
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "s.db")
    cfg.notify.digest_path = str(tmp_path / "d.html")
    s = run_once(cfg, [src])
    assert s.sources["greenhouse"]["skipped_records"] == 2
    assert "| greenhouse | ok | 0 | 2 |" in (tmp_path / "funnel.md").read_text(encoding="utf-8")


# L4 — rejected_samples hold real rejections, not records that were already seen/delivered.
def test_l4_rejected_samples_exclude_known_records(tmp_path):
    from job_scout.config import AppConfig
    from job_scout.pipeline import run_once
    from fixtures.gate0 import gate0_sources

    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "s.db")
    cfg.notify.digest_path = str(tmp_path / "d.html")
    run_once(cfg, gate0_sources())
    s2 = run_once(cfg, gate0_sources())
    assert all(x["reason"] not in ("not_new", "already_notified") for x in s2.internship_funnel["rejected_samples"])
