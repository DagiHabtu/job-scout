"""Known-programs calendar (S6) — unit tests for timing, staleness, identity, verdicts, maintenance.

Rewritten for S6 (the round/program data model changed: state, dated evidence, per-state identity,
no fixed LEAD_DAYS). The pipeline-level Case A/B/C acceptance lives in
tests/test_known_programs_acceptance.py.
"""

from __future__ import annotations

from datetime import date, timedelta

import job_scout.sources.known_programs as kp
from job_scout.sources.known_programs import (
    _PROGRAMS,
    KnownProgramsSource,
    _Program,
    _Round,
    effective_state,
    geo_evidence,
    geo_verdict,
    maintenance_notes,
    validate_table,
)

T = date(2027, 1, 10)


def _prog(name="P", rounds=(), **kw):
    base = dict(org=name, url=f"https://{name}/", stipend="$1", summary="s", geo_scope="worldwide",
                geo_quote="open to everyone", geo_url=f"https://{name}/rules", geo_checked_on=T)
    base.update(kw)
    return _Program(name=name, rounds=tuple(rounds), **base)


def _round(key="r1", opens=T, deadline=T + timedelta(days=10), state="open", checked=T):
    return _Round(key, opens, deadline, "period", state, "https://state/", checked)


def _fetch(today, *progs):
    src = KnownProgramsSource(today=today, programs=tuple(progs))
    return src.fetch(cfg=None), src.report


def test_lead_windows_by_state():
    opens = T + timedelta(days=40)
    for state, lead in (("announced", 30), ("expected", 51)):
        r = _round(opens=opens, deadline=opens + timedelta(days=7), state=state)
        assert _fetch(opens - timedelta(days=lead), _prog(rounds=[r]))[0]                    # first day in
        out, rep = _fetch(opens - timedelta(days=lead + 1), _prog(rounds=[r]))
        assert out == [] and rep["r1"] == "outside_lead_window"
    r = _round(opens=T + timedelta(days=90), deadline=T + timedelta(days=100), state="open")
    assert _fetch(T, _prog(rounds=[r]))[0]                                                    # open: no lead needed


def test_deadline_boundaries():
    r = _round(deadline=T)
    assert _fetch(T, _prog(rounds=[r]))[0]                                                    # on the deadline
    out, rep = _fetch(T + timedelta(days=1), _prog(rounds=[r]))
    assert out == [] and rep["r1"] == "deadline_passed" and rep["P"].startswith("no_published_round")


def test_stale_open_state_becomes_expected_and_title_says_so():
    r = _round(state="open", checked=T - timedelta(days=46))
    assert effective_state(r, T) == "expected"
    o = _fetch(T, _prog(rounds=[r]))[0][0]
    # identity keeps the recorded state (S6 review H1: staleness must not re-announce an open round)
    assert o.ats_job_id == "r1@open" and "dates not published" in o.title
    assert effective_state(_round(state="open", checked=T - timedelta(days=45)), T) == "open"


def test_titles_per_state():
    p = _prog(rounds=[_round(opens=date(2027, 2, 5), deadline=date(2027, 2, 12), state="announced", checked=T)])
    o = _fetch(date(2027, 1, 20), p)[0][0]
    assert o.title == "P — opens Feb 5, 2027"
    p = _prog(rounds=[_round(opens=date(2027, 1, 5), deadline=date(2027, 2, 12), state="open")])
    assert _fetch(T, p)[0][0].title == "P — applications open (deadline Feb 12, 2027)"


def test_geo_verdict_rules():
    _fetch(T, _prog("W", [_round("w1")]))
    assert geo_verdict("w1@open", "Ethiopia") == "eligible"
    _fetch(T, _prog("X", [_round("x1")], geo_exclusions=("Ethiopia",)))
    assert geo_verdict("x1@open", "Ethiopia") == "excluded"
    _fetch(T, _prog("U", [_round("u1")], geo_scope="unknown"))
    assert geo_verdict("u1@open", "Ethiopia") == "unknown"
    _fetch(T, _prog("S", [_round("s1")], geo_checked_on=T - timedelta(days=366)))
    assert geo_verdict("s1@open", "Ethiopia") == "unknown"                                    # stale rule
    _fetch(T, _prog("E", [_round("e1")], embargo_rule=True))
    assert geo_verdict("e1@open", "Iran") == "excluded"
    assert geo_verdict("e1@open", "Ethiopia") == "eligible"
    assert geo_verdict("nope@open", "Ethiopia") == "unknown"


def test_embargo_rule_unverified_is_unknown(monkeypatch):
    monkeypatch.setattr(kp, "US_EMBARGOED_CHECKED_ON", None)
    _fetch(T, _prog("E2", [_round("e2")], embargo_rule=True))
    assert geo_verdict("e2@open", "Ethiopia") == "unknown"


def test_geo_evidence_quotes_rule_url_date_and_conditions():
    _fetch(T, _prog("C", [_round("c1")], conditions=("18+", "30 hours/week")))
    ev = " | ".join(geo_evidence("c1@open"))
    assert "open to everyone" in ev and "https://C/rules" in ev and T.isoformat() in ev
    assert "condition (not checked): 18+" in ev and "30 hours/week" in ev


def test_shipped_table_is_valid_and_quiet_on_2026_10_04():
    assert validate_table(_PROGRAMS) == []
    out, rep = _fetch(date(2026, 10, 4), *_PROGRAMS)
    assert out == []
    assert rep["outreachy-2027-05"] == "outside_lead_window"
    assert rep["lfx-2027-spring"] == "outside_lead_window"
    assert rep["MLH Fellowship"].startswith("no_published_round")


def test_shipped_table_first_surfacing_dates():
    # Outreachy May 2027 (expected, opens ~Feb 5) from Dec 16; LFX spring (opens ~Jan 15) from Nov 25.
    keys = lambda d: {o.ats_job_id for o in _fetch(d, *_PROGRAMS)[0]}  # noqa: E731
    assert "lfx-2027-spring@expected" in keys(date(2026, 11, 25)) and "lfx-2027-spring@expected" not in keys(date(2026, 11, 24))
    assert "outreachy-2027-05@expected" in keys(date(2026, 12, 16)) and "outreachy-2027-05@expected" not in keys(date(2026, 12, 15))


def test_shipped_table_has_a_round_more_than_60_days_ahead():
    # Maintenance tripwire: fails when the calendar has run dry and needs refreshing.
    today = date.today()
    assert any(r.apply_deadline > today + timedelta(days=60) for p in _PROGRAMS for r in p.rounds)


def test_maintenance_notes_list_stale_checks_and_missing_rounds():
    notes = "\n".join(maintenance_notes(date(2026, 11, 10)))
    assert "re-check: https://www.outreachy.org/docs/applicant/" in notes
    assert "MLH Fellowship: no_published_round" in notes
    assert maintenance_notes(date(2026, 10, 4), (_prog(rounds=[_round(deadline=date(2026, 12, 1), checked=date(2026, 10, 1))]),)) == []
