"""S6 acceptance (spec §5 S6) — Case A (a qualifying round), B (nothing qualifies, every miss has a
reason), C (open round, geography unverified → surfaced as uncertain), state change announced once
per state, and the shipped table on 2026-10-04 (zero program notifications is the correct result)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from job_scout.config import AppConfig
from job_scout.models import EligibilityCategory, EmploymentType
from job_scout.pipeline import run_once
from job_scout.sources.known_programs import _PROGRAMS, KnownProgramsSource, _Program, _Round, validate_table
from job_scout.store import connect

T = date(2027, 3, 1)


def _program(name, rounds, **kw):
    base = dict(org=name, url=f"https://{name.lower()}.example/", stipend="$1", summary="A program.",
                geo_scope="worldwide", geo_quote=f"{name} is open worldwide.", geo_url=f"https://{name.lower()}.example/rules",
                geo_checked_on=T, conditions=("18+", "20 hours/week"))
    base.update(kw)
    return _Program(name=name, rounds=tuple(rounds), **base)


def _rnd(key, opens, deadline, state="open", checked=T):
    return _Round(key, opens, deadline, "period", state, "https://state.example/", checked)


A = (_program("A", [_rnd("a-r1", T - timedelta(days=3), T + timedelta(days=10))]),)
B1 = (_program("MLH Fellowship", [_rnd("mlh-2026-fall", date(2026, 8, 1), date(2026, 8, 31), checked=date(2026, 10, 4))],
               geo_checked_on=date(2026, 10, 4)),)
B2 = (_program("B2", [_rnd("b2-r1", T + timedelta(days=90), T + timedelta(days=97), state="expected")]),)
B3 = (_program("B3", []),)
B4 = (_program("B4", [_rnd("b4-r1", T - timedelta(days=3), T + timedelta(days=10))], geo_exclusions=("Ethiopia",)),)
C = (_program("C", [_rnd("c-r1", T - timedelta(days=3), T + timedelta(days=10))], geo_scope="unknown"),)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                 # data/notify.md is read relative to the run directory
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    db = connect(cfg.db_path)
    yield cfg, db
    db.close()


def _md():
    return Path("data/notify.md").read_text(encoding="utf-8")


def test_acquisition_shipped_table(env):
    cfg, _ = env
    assert validate_table(_PROGRAMS) == []
    KnownProgramsSource(today=T).fetch(cfg.sources)           # does not raise


def test_case_a_qualifying_round(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=T, programs=A)], today=T, conn=db)
    o = s.ranked[0]
    assert s.sources["known_programs"]["count"] == 1
    assert o.ats_job_id == "a-r1@open" and o.employment_type == EmploymentType.STIPEND_PROGRAM
    assert o.eligibility.category == EligibilityCategory.STIPEND_PROGRAM_GLOBAL
    ev = " ".join(o.eligibility.evidence)
    assert A[0].geo_quote in ev and A[0].geo_url in ev
    assert o.deadline == T + timedelta(days=10)
    assert s.notified == 1
    md = _md()
    assert all(x in md for x in (o.title, A[0].url, A[0].geo_quote, *A[0].conditions))
    assert md.index("Apply") < md.index(o.title)          # "Actionable" renamed "Apply" (§12 S11)
    s2 = run_once(cfg, [KnownProgramsSource(today=T, programs=A)], today=T, conn=db)
    assert s2.notified == 0 and s2.gate["already_notified"] == 1


def test_case_b1_closed_mlh_round(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=date(2026, 10, 4), programs=B1)], today=date(2026, 10, 4), conn=db)
    assert s.notified == 0 and s.sources["known_programs"]["count"] == 0
    assert s.sources["known_programs"]["report"]["mlh-2026-fall"] == "deadline_passed"


def test_case_b2_outside_lead_window(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=T, programs=B2)], today=T, conn=db)
    assert s.notified == 0 and s.sources["known_programs"]["report"]["b2-r1"] == "outside_lead_window"


def test_case_b3_no_rounds(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=T, programs=B3)], today=T, conn=db)
    assert s.notified == 0 and s.sources["known_programs"]["report"]["B3"].startswith("no_published_round")


def test_case_b4_user_country_excluded(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=T, programs=B4)], today=T, conn=db)
    assert s.sources["known_programs"]["count"] == 1 and s.notified == 0
    assert s.rejects["eligibility:remote_excludes_user"] == 1


def test_case_c_unverified_geography_is_surfaced_as_uncertain(env):
    cfg, db = env
    s = run_once(cfg, [KnownProgramsSource(today=T, programs=C)], today=T, conn=db)
    o = s.ranked[0]
    assert o.eligibility.category == EligibilityCategory.UNKNOWN
    assert "not verified" in " ".join(o.eligibility.evidence)
    assert s.notified == 1
    md = _md()
    assert md.index("Check eligibility") < md.index(o.title)
    assert "Actionable" not in md


def test_state_change_is_announced_once_per_state(env):
    cfg, db = env
    t0, t1 = T - timedelta(days=20), T
    expected = (_program("S", [_rnd("s-r1", T - timedelta(days=3), T + timedelta(days=10), state="expected")]),)
    opened = (_program("S", [_rnd("s-r1", T - timedelta(days=3), T + timedelta(days=10), state="open")]),)
    s0 = run_once(cfg, [KnownProgramsSource(today=t0, programs=expected)], today=t0, conn=db)
    assert s0.notified == 1 and s0.ranked[0].ats_job_id == "s-r1@expected"
    s1 = run_once(cfg, [KnownProgramsSource(today=t1, programs=opened)], today=t1, conn=db)
    assert s1.notified == 1 and s1.ranked[0].ats_job_id == "s-r1@open"


def test_shipped_table_on_2026_10_04_notifies_nothing(env):
    cfg, db = env
    d = date(2026, 10, 4)
    s = run_once(cfg, [KnownProgramsSource(today=d)], today=d, conn=db)
    assert s.notified == 0
    report = s.sources["known_programs"]["report"]
    assert "no_published_round" in report["MLH Fellowship"]
    assert report["outreachy-2027-05"] == "outside_lead_window"
