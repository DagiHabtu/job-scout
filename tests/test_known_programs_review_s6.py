"""S6 independent review — every finding as a test (written before the fixes; see STATE.md pass log)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

import job_scout.sources.known_programs as kp
from job_scout.config import AppConfig
from job_scout.models import Lifecycle, Opportunity
from job_scout.notify import gate_reason
from job_scout.pipeline import run_once
from job_scout.sources.known_programs import (
    _PROGRAMS,
    KnownProgramsSource,
    _Program,
    _Round,
    geo_verdict,
    maintenance_notes,
    validate_table,
)
from job_scout.store import connect

T = date(2027, 3, 1)


def _prog(name, rounds, **kw):
    base = dict(org=name, url=f"https://{name}/", stipend="$1", summary="s", geo_scope="worldwide",
                geo_quote="open to everyone", geo_url=f"https://{name}/rules", geo_checked_on=T)
    base.update(kw)
    return _Program(name=name, rounds=tuple(rounds), **base)


def _rnd(key, opens=T - timedelta(days=1), deadline=T + timedelta(days=80), state="open", checked=T):
    return _Round(key, opens, deadline, "period", state, "https://state/", checked)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    db = connect(cfg.db_path)
    yield cfg, db
    db.close()


# H1 — an open round that goes stale must not be announced again as "expected".
def test_h1_stale_open_round_is_not_renotified(env):
    cfg, db = env
    progs = (_prog("H", [_rnd("q1")]),)
    s1 = run_once(cfg, [KnownProgramsSource(today=T, programs=progs)], today=T, conn=db)
    assert s1.notified == 1
    later = T + timedelta(days=46)                       # state check now stale (>45 days)
    s2 = run_once(cfg, [KnownProgramsSource(today=later, programs=progs)], today=later, conn=db)
    assert s2.notified == 0
    assert "dates not published" in s2.ranked[0].title   # the title still says the check is stale


def test_h1_forward_state_change_is_still_announced(env):
    cfg, db = env
    t0 = T - timedelta(days=40)
    exp = (_prog("F", [_rnd("f1", opens=T, deadline=T + timedelta(days=7), state="expected", checked=t0)]),)
    opn = (_prog("F", [_rnd("f1", opens=T, deadline=T + timedelta(days=7), state="open", checked=T)]),)
    assert run_once(cfg, [KnownProgramsSource(today=t0, programs=exp)], today=t0, conn=db).notified == 1
    assert run_once(cfg, [KnownProgramsSource(today=T, programs=opn)], today=T, conn=db).notified == 1


# H2 — duplicate round keys must not let one program borrow another's verdict.
def test_h2_validate_table_rejects_duplicate_round_keys():
    progs = (_prog("A", [_rnd("dup")]), _prog("B", [_rnd("dup")], geo_scope="unknown"))
    assert any("duplicate" in p for p in validate_table(progs))


def test_h2_fetch_with_duplicate_keys_fails_loudly():
    progs = (_prog("A", [_rnd("dup")]), _prog("B", [_rnd("dup")], geo_scope="unknown"))
    with pytest.raises(ValueError):
        KnownProgramsSource(today=T, programs=progs).fetch(None)


# M1 — "eligible" requires the quote and the URL, even if validate_table was never run.
@pytest.mark.parametrize("missing", ["geo_quote", "geo_url"])
def test_m1_worldwide_without_evidence_is_unknown(missing):
    KnownProgramsSource(today=T, programs=(_prog("M", [_rnd("m1")], **{missing: ""}),)).fetch(None)
    assert geo_verdict("m1@open", "Ethiopia") == "unknown"


# M2 — a lookup miss must not overwrite injected programs with the shipped table.
def test_m2_lookup_miss_does_not_replace_injected_program():
    KnownProgramsSource(today=T, programs=(_prog("G", [_rnd("gsoc-2027")], geo_scope="unknown"),)).fetch(None)
    assert geo_verdict("gsoc-2027@open", "Ethiopia") == "unknown"
    geo_verdict("not-in-index@open", "Ethiopia")             # a miss
    assert geo_verdict("gsoc-2027@open", "Ethiopia") == "unknown"


def test_m2_each_fetch_replaces_the_index():
    KnownProgramsSource(today=T, programs=(_prog("Z", [_rnd("z1")]),)).fetch(None)
    KnownProgramsSource(today=T, programs=(_prog("Y", [_rnd("y1")]),)).fetch(None)
    assert geo_verdict("z1@open", "Ethiopia") == "unknown"     # not left over from the earlier fetch


# L1 — the embargo list goes stale like any other check, and the heartbeat asks for a re-check.
def test_l1_stale_embargo_list_makes_embargo_programs_unknown(monkeypatch):
    monkeypatch.setattr(kp, "US_EMBARGOED_CHECKED_ON", T - timedelta(days=366))
    KnownProgramsSource(today=T, programs=(_prog("E", [_rnd("e1")], embargo_rule=True),)).fetch(None)
    assert geo_verdict("e1@open", "Ethiopia") == "unknown"


def test_l1_heartbeat_lists_stale_embargo_list(monkeypatch):
    monkeypatch.setattr(kp, "US_EMBARGOED_CHECKED_ON", T - timedelta(days=31))
    notes = "\n".join(maintenance_notes(T, (_prog("E", [_rnd("e1")], embargo_rule=True),)))
    assert f"re-check: {kp.US_EMBARGOED_URL}" in notes


# L2 — embargoed places written as ISO codes or official names still match.
@pytest.mark.parametrize("country", ["IR", "Islamic Republic of Iran", "DPRK",
                                     "Democratic People's Republic of Korea", "CU", "KP"])
def test_l2_embargo_aliases(country):
    KnownProgramsSource(today=T, programs=(_prog("E", [_rnd("e1")], embargo_rule=True),)).fetch(None)
    assert geo_verdict("e1@open", country) == "excluded"


# L3 — pin the gate order: an already-delivered ACTIVE record reads already_notified (deviation j).
def test_l3_gate_order_already_notified_before_not_new():
    o = Opportunity(title="t", company="c", apply_url="u", canonical_url="u", status=Lifecycle.ACTIVE)
    assert gate_reason(o, 0.4) == "not_new"
    o.notified_at = datetime(2026, 1, 1)
    assert gate_reason(o, 0.4) == "already_notified"


# L4 — pin the shipped verdicts for Ethiopia; maintenance "fresh" with a past check date.
def test_l4_shipped_verdicts_for_ethiopia():
    KnownProgramsSource(today=date(2026, 10, 4)).fetch(None)
    assert geo_verdict("outreachy-2027-05@expected", "Ethiopia") == "eligible"
    assert geo_verdict("gsoc-2027@expected", "Ethiopia") == "eligible"
    assert geo_verdict("lfx-2027-spring@expected", "Ethiopia") == "unknown"


def test_l4_maintenance_fresh_checks_are_quiet():
    checked = T - timedelta(days=30)
    p = _prog("Q", [_rnd("q1", deadline=T + timedelta(days=90), checked=checked)], geo_checked_on=checked)
    assert maintenance_notes(T, (p,)) == []
    assert validate_table(_PROGRAMS) == []


# M3 — the MLH row: verified no-projects list; Ethiopia not on it (no round, so no notification).
def test_m3_mlh_exclusions_verified():
    mlh = next(p for p in _PROGRAMS if p.name == "MLH Fellowship")
    assert len(mlh.geo_exclusions) == 30 and "Ethiopia" not in mlh.geo_exclusions and mlh.rounds == ()
    assert mlh.url == "https://fellowship.mlh.com/"
