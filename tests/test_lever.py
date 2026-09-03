"""Lever adapter — hermetic tests against a RECORDED real board snapshot (leverdemo). No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.config import AppConfig
from job_scout.models import EmploymentType, RemoteStatus
from job_scout.pipeline import run_once
from job_scout.sources.lever import (
    _POSTINGS_URL,
    LeverSource,
    _employment,
    _remote,
)

FIXTURE = Path(__file__).parent / "fixtures" / "lever_postings.json"
_RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
SITE = _RAW["site"]
POSTINGS = _RAW["postings"]


def _router(postings=None, *, error=None):
    postings = POSTINGS if postings is None else postings

    def fetch_json(url):
        assert url == _POSTINGS_URL.format(site=SITE), url
        if error is not None:
            raise error
        return postings

    return fetch_json


def _fetch(**kw):
    return LeverSource(sites=[SITE], fetch_json=_router(**kw)).fetch(cfg=None)


# --- mapping helpers -------------------------------------------------------------------------- #


def test_employment_mapping():
    assert _employment("Internship") == EmploymentType.INTERNSHIP
    assert _employment("Regular Full Time (Salary)") == EmploymentType.FULL_TIME
    assert _employment("Contract") == EmploymentType.CONTRACT
    assert _employment("Part-time") == EmploymentType.UNKNOWN     # no part-time enum → honest UNKNOWN
    assert _employment(None) == EmploymentType.UNKNOWN


def test_remote_mapping():
    assert _remote("remote") == RemoteStatus.REMOTE
    assert _remote("on-site") == RemoteStatus.ONSITE
    assert _remote("hybrid") == RemoteStatus.HYBRID
    assert _remote("unspecified") == RemoteStatus.UNKNOWN
    assert _remote(None) == RemoteStatus.UNKNOWN


# --- parsing ---------------------------------------------------------------------------------- #


def test_parses_records_with_identity_and_mapped_fields():
    opps = _fetch()
    assert len(opps) == len(POSTINGS)
    first = opps[0]
    assert first.title == POSTINGS[0]["text"]
    assert first.company == "Leverdemo"                       # prettified slug
    assert first.ats_provider == "lever"
    assert first.ats_job_id == POSTINGS[0]["id"]
    assert first.apply_url == POSTINGS[0]["hostedUrl"]
    assert first.location_raw == POSTINGS[0]["categories"]["location"]
    assert first.remote_status == RemoteStatus.REMOTE          # workplaceType "remote"
    # a posting with a Full-Time commitment maps through
    ft = next(o for o in opps if o.title == "C++ Software Developer")
    assert ft.employment_type == EmploymentType.FULL_TIME and ft.remote_status == RemoteStatus.HYBRID


def test_derived_fields_left_for_pipeline_and_text_is_clean():
    opp = _fetch()[0]
    assert opp.canonical_url == "" and opp.content_fingerprint == ""
    assert "<" not in opp.description and "&lt;" not in opp.description


def test_empty_description_is_handled():
    opp = next(o for o in _fetch() if o.title == "C++ Software Developer")
    assert opp.description == ""                               # descriptionPlain was empty


# --- failure semantics ------------------------------------------------------------------------ #


def test_malformed_posting_is_skipped():
    good = POSTINGS[0]
    bad = {"id": "x", "hostedUrl": "https://x"}                # no 'text' → malformed
    opps = _fetch(postings=[good, bad])
    assert len(opps) == 1 and opps[0].title == good["text"]


def test_all_sites_failing_raises():
    src = LeverSource(sites=[SITE], fetch_json=_router(error=ConnectionError("down")))
    with pytest.raises(RuntimeError):
        src.fetch(cfg=None)


def test_non_array_response_is_a_total_failure():
    # The documented Lever gotcha: an HTML page (→ get_json raises) or any non-array is a failure,
    # never mistaken for "no jobs".
    src = LeverSource(sites=[SITE], fetch_json=lambda url: {"unexpected": "object"})
    with pytest.raises(RuntimeError):
        src.fetch(cfg=None)


def test_one_site_isolated_when_another_succeeds():
    other = "otherco"

    def fetch_json(url):
        if url == _POSTINGS_URL.format(site=other):
            raise ConnectionError("boom")
        return POSTINGS

    opps = LeverSource(sites=[SITE, other], fetch_json=fetch_json).fetch(cfg=None)
    assert len(opps) == len(POSTINGS)


def test_no_sites_returns_empty():
    assert LeverSource(sites=[], fetch_json=_router()).fetch(cfg=None) == []


# --- composition with the frozen pipeline ----------------------------------------------------- #


def test_real_records_flow_through_the_pipeline(tmp_path):
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")

    summary = run_once(cfg, [LeverSource(sites=[SITE], fetch_json=_router())])
    assert summary.sources["lever"]["ok"] is True
    assert summary.discovered == len(POSTINGS)
    for o in summary.ranked:
        assert o.canonical_url and o.content_fingerprint
        assert o.eligibility is not None and o.relevance is not None
    summary2 = run_once(cfg, [LeverSource(sites=[SITE], fetch_json=_router())])
    assert summary2.lifecycle["new"] == 0
