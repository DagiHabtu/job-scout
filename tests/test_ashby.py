"""Ashby adapter — hermetic tests against a RECORDED real board snapshot (ashby org). No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.config import AppConfig
from job_scout.models import EmploymentType, RemoteStatus
from job_scout.pipeline import run_once
from job_scout.sources.ashby import (
    _BOARD_URL,
    AshbySource,
    _employment,
    _remote,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ashby_board.json"
_RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
ORG = _RAW["org"]
JOBS = _RAW["jobs"]


def _router(jobs=None, *, error=None):
    jobs = JOBS if jobs is None else jobs

    def fetch_json(url):
        assert url == _BOARD_URL.format(org=ORG), url
        if error is not None:
            raise error
        return {"jobs": jobs}

    return fetch_json


def _fetch(**kw):
    return AshbySource(orgs=[ORG], fetch_json=_router(**kw)).fetch(cfg=None)


def test_employment_mapping():
    assert _employment("FullTime") == EmploymentType.FULL_TIME
    assert _employment("Intern") == EmploymentType.INTERNSHIP
    assert _employment("Contract") == EmploymentType.CONTRACT
    assert _employment("Temporary") == EmploymentType.CONTRACT
    assert _employment("PartTime") == EmploymentType.UNKNOWN
    assert _employment(None) == EmploymentType.UNKNOWN


def test_remote_mapping_prefers_workplace_then_isremote():
    assert _remote({"workplaceType": "Remote"}) == RemoteStatus.REMOTE
    assert _remote({"workplaceType": "Hybrid"}) == RemoteStatus.HYBRID
    assert _remote({"workplaceType": "Onsite"}) == RemoteStatus.ONSITE
    assert _remote({"isRemote": True}) == RemoteStatus.REMOTE       # fallback when no workplaceType
    assert _remote({}) == RemoteStatus.UNKNOWN


def test_parses_records_with_identity_and_clean_text():
    opps = _fetch()
    assert len(opps) == len(JOBS)
    first = opps[0]
    assert first.title == JOBS[0]["title"]
    assert first.company == "Ashby"
    assert first.ats_provider == "ashby"
    assert first.ats_job_id == JOBS[0]["id"]
    assert first.apply_url == JOBS[0]["jobUrl"]
    assert first.location_raw == JOBS[0]["location"]
    assert first.remote_status == RemoteStatus.REMOTE
    assert first.employment_type == EmploymentType.FULL_TIME
    assert first.description and "<" not in first.description and "&lt;" not in first.description


def test_unlisted_jobs_are_skipped():
    hidden = dict(JOBS[0], id="hidden-1", isListed=False)
    opps = _fetch(jobs=[hidden, JOBS[1]])
    assert [o.ats_job_id for o in opps] == [JOBS[1]["id"]]


def test_malformed_job_is_skipped():
    bad = {"id": "x", "jobUrl": "https://x"}                        # no title
    opps = _fetch(jobs=[JOBS[0], bad])
    assert len(opps) == 1 and opps[0].title == JOBS[0]["title"]


def test_all_orgs_failing_raises():
    with pytest.raises(RuntimeError):
        AshbySource(orgs=[ORG], fetch_json=_router(error=ConnectionError("down"))).fetch(cfg=None)


def test_one_org_isolated_when_another_succeeds():
    other = "otherco"

    def fetch_json(url):
        if url == _BOARD_URL.format(org=other):
            raise ConnectionError("boom")
        return {"jobs": JOBS}

    opps = AshbySource(orgs=[ORG, other], fetch_json=fetch_json).fetch(cfg=None)
    assert len(opps) == len(JOBS)


def test_no_orgs_returns_empty():
    assert AshbySource(orgs=[], fetch_json=_router()).fetch(cfg=None) == []


def test_us_only_role_is_excluded_by_eligibility_through_pipeline(tmp_path):
    # "Remote - US" (job 3) must be dropped for an ET user — end-to-end proof the adapter composes
    # with the eligibility gate.
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    summary = run_once(cfg, [AshbySource(orgs=[ORG], fetch_json=_router())])
    assert summary.sources["ashby"]["ok"] is True
    assert summary.discovered == len(JOBS)
    assert not any("Product Designer" in o.title for o in summary.ranked)   # the Remote-US role
    for o in summary.ranked:
        assert o.canonical_url and o.content_fingerprint and o.eligibility is not None
