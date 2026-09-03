"""Greenhouse adapter — hermetic parser tests against a RECORDED real board snapshot.

The fixture `greenhouse_board.json` is a trimmed, real capture from
`boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true` (see scratch recorder). No network is
touched here: the HTTP layer is injected. Also proves the adapter composes with the frozen pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.config import AppConfig
from job_scout.models import EmploymentType, RemoteStatus
from job_scout.pipeline import run_once
from job_scout.sources.greenhouse import (
    _BOARD_URL,
    _JOBS_URL,
    GreenhouseSource,
    _html_to_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_board.json"
_RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))
TOKEN = _RAW["board_token"]
COMPANY = _RAW["_board_meta"]["name"]
JOBS = _RAW["jobs"]


def _router(jobs=None, meta_name=COMPANY, *, jobs_error=None):
    """Build an injectable fetch_json that answers the board-meta and jobs URLs from the fixture."""
    jobs = JOBS if jobs is None else jobs

    def fetch_json(url):
        if url == _BOARD_URL.format(token=TOKEN):
            return {"name": meta_name}
        if url == _JOBS_URL.format(token=TOKEN):
            if jobs_error is not None:
                raise jobs_error
            return {"jobs": jobs}
        raise AssertionError(f"unexpected URL {url!r}")

    return fetch_json


def _fetch(**kw):
    return GreenhouseSource(boards=[TOKEN], fetch_json=_router(**kw)).fetch(cfg=None)


# --- parsing --------------------------------------------------------------------------------- #


def test_parses_all_records_with_identity_and_clean_text():
    opps = _fetch()
    assert len(opps) == len(JOBS)
    first = opps[0]
    assert first.title == JOBS[0]["title"]
    assert first.company == COMPANY
    assert first.ats_provider == "greenhouse"
    assert first.ats_job_id == str(JOBS[0]["id"])
    assert first.apply_url == JOBS[0]["absolute_url"]
    assert first.location_raw == JOBS[0]["location"]["name"]
    # description is decoded plain text, not raw/encoded HTML
    assert first.description
    assert "<" not in first.description and "&lt;" not in first.description and "&amp;" not in first.description


def test_leaves_derived_fields_for_the_pipeline():
    opp = _fetch()[0]
    assert opp.canonical_url == ""                 # normalize computes this
    assert opp.content_fingerprint == ""           # normalize computes this
    assert opp.remote_status == RemoteStatus.UNKNOWN
    assert opp.employment_type == EmploymentType.UNKNOWN
    assert opp.eligibility is None and opp.relevance is None


def test_html_to_text_decodes_entities_and_strips_tags():
    raw = "&lt;p&gt;Build in &lt;b&gt;Python&lt;/b&gt; &amp; SQL.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Remote&lt;/li&gt;&lt;/ul&gt;"
    assert _html_to_text(raw) == "Build in Python & SQL. Remote"


# --- failure semantics (the frozen Source contract) ------------------------------------------ #


def test_malformed_record_is_skipped_not_fatal():
    good = JOBS[0]
    bad = {"id": 1, "absolute_url": "https://x/1"}   # no title → malformed
    opps = _fetch(jobs=[good, bad, JOBS[1] if len(JOBS) > 1 else good])
    assert all(o.title for o in opps)
    assert len(opps) == 2                             # the bad one dropped, the two good kept


def test_all_boards_failing_raises_total_failure():
    src = GreenhouseSource(boards=[TOKEN], fetch_json=_router(jobs_error=ConnectionError("network down")))
    with pytest.raises(RuntimeError):
        src.fetch(cfg=None)


def test_one_board_failing_is_isolated_when_another_succeeds():
    ok_router = _router()
    fail_url = _JOBS_URL.format(token="deadbeef")

    def fetch_json(url):
        if url == _BOARD_URL.format(token="deadbeef"):
            return {"name": "Dead"}
        if url == fail_url:
            raise ConnectionError("boom")
        return ok_router(url)

    src = GreenhouseSource(boards=[TOKEN, "deadbeef"], fetch_json=fetch_json)
    opps = src.fetch(cfg=None)                        # good board's jobs returned; no raise
    assert len(opps) == len(JOBS)


def test_no_boards_configured_returns_empty():
    assert GreenhouseSource(boards=[], fetch_json=_router()).fetch(cfg=None) == []


def test_board_metadata_failure_falls_back_to_token():
    def fetch_json(url):
        if url == _BOARD_URL.format(token=TOKEN):
            raise ConnectionError("meta down")
        return {"jobs": JOBS}

    opps = GreenhouseSource(boards=[TOKEN], fetch_json=fetch_json).fetch(cfg=None)
    assert opps and opps[0].company == TOKEN.title()   # prettified token fallback ('gitlab' → 'Gitlab')


# --- composition with the frozen pipeline ----------------------------------------------------- #


def test_real_records_flow_through_the_pipeline(tmp_path):
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    src = GreenhouseSource(boards=[TOKEN], fetch_json=_router())

    summary = run_once(cfg, [src])
    assert summary.sources["greenhouse"]["ok"] is True
    assert summary.discovered == len(JOBS)
    # every surviving record was normalized (canonical URL + fingerprint) and eligibility-classified
    for o in summary.ranked:
        assert o.canonical_url and o.content_fingerprint
        assert o.eligibility is not None and o.relevance is not None
    # second run over the same store reconciles to ACTIVE, not NEW
    summary2 = run_once(cfg, [GreenhouseSource(boards=[TOKEN], fetch_json=_router())])
    assert summary2.lifecycle["new"] == 0
