"""S0 — reason-coded funnel: every record that does not reach the user carries exactly one reason."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory, EmploymentType, Lifecycle, Opportunity, Relevance
from job_scout.notify import gate_reason
from job_scout.pipeline import run_once
from job_scout.score import filter_reason

from fixtures.gate0 import FakeSource, gate0_sources


def _cfg(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    return cfg


def _invariants(s):
    assert sum(s.rejects.values()) == s.after_dedupe - s.after_filter
    assert sum(s.gate.values()) == s.after_filter - s.notified
    merged = s.discovered - s.after_dedupe
    assert s.discovered - merged - sum(s.rejects.values()) - sum(s.gate.values()) == s.notified


def test_funnel_invariants_hold_on_both_runs(tmp_path):
    cfg = _cfg(tmp_path)
    s1 = run_once(cfg, gate0_sources())
    _invariants(s1)
    assert s1.rejects == {"eligibility:requires_work_auth": 1}
    s2 = run_once(cfg, gate0_sources())
    _invariants(s2)
    # everything known → one reason each (S6: a delivered record reads already_notified first)
    assert s2.gate == {"already_notified": 4}    # all 4 survivors were delivered on run 1 (pinned, S6 review L3)


def test_run_record_carries_histograms_and_funnel_file(tmp_path):
    cfg = _cfg(tmp_path)
    s = run_once(cfg, gate0_sources())
    assert sum(s.by_type.values()) == s.discovered
    assert sum(s.by_eligibility.values()) == s.after_dedupe
    rec = json.loads(sqlite3.connect(cfg.db_path).execute("SELECT summary FROM runs").fetchone()[0])
    for k in ("rejects", "gate", "by_type", "by_eligibility", "near_misses", "internship_funnel"):
        assert k in rec
    md = (Path(tmp_path) / "funnel.md").read_text(encoding="utf-8")
    assert "eligibility:requires_work_auth" in md and "notified" in md


def test_internship_funnel_accounts_for_every_fetched_target_record(tmp_path):
    s = run_once(_cfg(tmp_path), gate0_sources())
    f = s.internship_funnel
    # gate0: 5 internships (incl. the 2 cross-source dups) + 1 stipend program
    assert f["fetched"] == 6
    assert sum(f["outcomes"].values()) == f["fetched"]
    assert f["outcomes"]["merged"] == 1
    assert f["outcomes"]["eligibility:requires_work_auth"] == 1
    assert f["rejected_samples"][0]["reason"]


def test_near_misses_are_unselected_survivors_ordered_by_score(tmp_path):
    cfg = _cfg(tmp_path)
    run_once(cfg, gate0_sources())
    s2 = run_once(cfg, gate0_sources())
    nm = s2.near_misses
    assert 0 < len(nm) <= 5
    assert [n["score"] for n in nm] == sorted((n["score"] for n in nm), reverse=True)
    assert all(n["gate_reason"] in ("not_new", "already_notified") for n in nm)


def test_source_report_is_copied_into_the_run_record(tmp_path):
    src = FakeSource("reporting", [])
    src.report = {"round-x": "deadline_passed"}
    s = run_once(_cfg(tmp_path), [src])
    assert s.sources["reporting"] == {"ok": True, "count": 0, "report": {"round-x": "deadline_passed"}}


def test_filter_reason_codes():
    cfg = AppConfig()
    o = Opportunity(title="t", company="c", apply_url="u", canonical_url="u")
    o.eligibility = Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.85)
    assert filter_reason(o, cfg.profile, cfg.scoring, date(2026, 1, 1)) == "eligibility:remote_excludes_user"
    o.eligibility = Eligibility(EligibilityCategory.UNKNOWN, 0.3)
    o.deadline = date(2025, 12, 31)
    assert filter_reason(o, cfg.profile, cfg.scoring, date(2026, 1, 1)) == "deadline_passed"
    o.deadline = None
    o.employment_type = EmploymentType.FULL_TIME
    assert filter_reason(o, cfg.profile, cfg.scoring, date(2026, 1, 1)) == "type_unwanted:full_time"
    o.employment_type = EmploymentType.UNKNOWN
    assert filter_reason(o, cfg.profile, cfg.scoring, date(2026, 1, 1)) is None


# test_gate_reason_codes (S0 interim gate) superseded by S5's deterministic gate: tests/test_gate.py
