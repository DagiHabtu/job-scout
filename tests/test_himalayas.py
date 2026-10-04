"""S7 — Himalayas adapter: mapping (recorded fixture), 429 handling, worldwide eligibility via S2."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from job_scout.config import AppConfig, SourceConfig
from job_scout.eligibility import classify_eligibility
from job_scout.models import EligibilityCategory as EC
from job_scout.models import EmploymentType as ET
from job_scout.models import RemoteStatus
from job_scout.normalize import normalize
from job_scout.sources.himalayas import HimalayasSource

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "himalayas_search.json").read_text(encoding="utf-8"))


def _src(responses, queries=("q1",)):
    calls = []

    def fetch(url):
        calls.append(url)
        r = responses(url) if callable(responses) else responses
        if isinstance(r, Exception):
            raise r
        return r

    return HimalayasSource(list(queries), fetch_json=fetch, sleep=lambda s: None), calls


def _429(url="u"):
    return urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO(b""))


def test_mapping_from_recorded_fixture():
    src, calls = _src(FIXTURE)
    opps = src.fetch(SourceConfig())
    assert len(calls) == 1                                    # short page → no page 2
    assert "sort=recent" in calls[0] and "page=1" in calls[0]
    by_title = {o.title: o for o in opps}
    swe = by_title["Software Engineer Intern"]
    assert swe.ats_provider == "himalayas" and swe.ats_job_id.startswith("https://himalayas.app/")
    assert swe.employment_type == ET.INTERNSHIP and swe.remote_status == RemoteStatus.REMOTE
    assert swe.location_raw == "Worldwide"
    assert swe.posting_date is not None and swe.deadline is not None
    assert "<" not in swe.description                          # HTML stripped
    restricted = by_title["Data Annotation Specialist (Remote / Part-Time)"]
    assert restricted.location_raw == "Ethiopia; Ghana; Kenya; Nigeria; Rwanda"
    assert restricted.employment_type == ET.NEW_GRAD           # "Part Time" + Entry-level seniority


@pytest.mark.parametrize("etype,seniority,expected", [
    ("Intern", ["Entry-level"], ET.INTERNSHIP),
    ("Full Time", ["Entry-level"], ET.NEW_GRAD),
    ("Full Time", ["Mid-level"], ET.FULL_TIME),
    ("Contractor", [], ET.CONTRACT),
    ("Part Time", [], ET.UNKNOWN),
])
def test_employment_mapping(etype, seniority, expected):
    job = dict(FIXTURE["jobs"][0], employmentType=etype, seniority=seniority)
    src, _ = _src({"jobs": [job], "limit": 20})
    assert src.fetch(SourceConfig())[0].employment_type == expected


def test_empty_restrictions_are_worldwide_through_s2():
    src, _ = _src(FIXTURE)
    profile = AppConfig().profile
    cats = {o.title: classify_eligibility(normalize(o), profile).category for o in src.fetch(SourceConfig())}
    assert cats["Software Engineer Intern"] == EC.WORLDWIDE_REMOTE
    assert cats["Data Annotation Specialist (Remote / Part-Time)"] == EC.REMOTE_REGION_INCLUDES_USER


def test_overlapping_queries_are_deduplicated_by_guid():
    src, _ = _src(FIXTURE, queries=("q1", "q2"))
    assert len(src.fetch(SourceConfig())) == len(FIXTURE["jobs"])


def test_paging_stops_on_short_page_and_429_keeps_earlier_pages():
    full = {"jobs": [dict(FIXTURE["jobs"][0], guid=f"https://himalayas.app/x/{i}") for i in range(20)], "limit": 20}

    def resp(url):
        return full if "page=1" in url else _429(url)

    src, calls = _src(resp)
    opps = src.fetch(SourceConfig())
    assert len(opps) == 20 and len(calls) == 2
    assert src.report["q1"].startswith("rate_limited")


def test_one_failing_query_is_isolated_all_failing_raises():
    def resp(url):
        return _429(url) if "bad" in url else FIXTURE

    src, _ = _src(resp, queries=("bad", "good"))
    assert len(src.fetch(SourceConfig())) == len(FIXTURE["jobs"])
    src, _ = _src(lambda url: _429(url), queries=("bad1", "bad2"))
    with pytest.raises(RuntimeError):
        src.fetch(SourceConfig())


def test_malformed_listing_is_skipped():
    src, _ = _src({"jobs": [{"title": "no guid"}, FIXTURE["jobs"][0]], "limit": 20})
    assert len(src.fetch(SourceConfig())) == 1


def test_default_queries_and_registry():
    from job_scout.cli import _REGISTRY

    assert len(SourceConfig().himalayas_queries) == 4
    assert "himalayas" in _REGISTRY
