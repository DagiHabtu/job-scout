"""Iteration 3 §4.6 — weekly digest, urgent-only daily, numbered items. Written before the code."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from job_scout.config import AppConfig
from job_scout.models import Eligibility, EligibilityCategory as EC, EmploymentType as ET, Lifecycle, Opportunity
from job_scout.notify import gate_reason, in_pending_pool, is_urgent, render_heartbeat_md
from job_scout.pipeline import _check_invariant, run_once
from job_scout.store import connect

from fixtures.gate0 import FakeSource

TUESDAY, MONDAY = date(2026, 10, 20), date(2026, 10, 26)


def _cfg(tmp_path) -> AppConfig:
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    cfg.notify.cadence = "weekly"
    return cfg


def _intern(title, deadline=None) -> Opportunity:
    slug = title.lower().replace(" ", "-")
    return Opportunity(title=title, company=f"Co {title}", apply_url=f"https://x.example/{slug}", canonical_url="",
                       description="Fully remote worldwide — work from anywhere. Build backend services in Python. "
                                   "Internship, entry level.",
                       employment_type=ET.INTERNSHIP, technologies=["python"], deadline=deadline)


def _sources(today):
    return [FakeSource("fake", [_intern("Backend Intern A", deadline=today + timedelta(days=10)),
                                _intern("Backend Intern B"), _intern("Backend Intern C")])]


def _after_monday_digest(cfg):
    """A weekday run needs this week's digest already stored; else it is the (first) digest (review M1)."""
    run_once(cfg, [FakeSource("empty", [])], today=MONDAY - timedelta(days=7))


def _notify(tmp_path) -> str:
    p = Path(tmp_path) / "notify.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _map(md: str) -> dict:
    m = re.search(r"<!-- scout-items (\{.*?\}) -->", md)
    assert m, "hidden map missing"
    return json.loads(m.group(1))


# --- pending pool ------------------------------------------------------------------------------ #

def _opp(status, notified_at=None):
    o = Opportunity(title="Backend Engineering Intern", company="C", apply_url="https://x", canonical_url="https://x",
                    employment_type=ET.INTERNSHIP, status=status, notified_at=notified_at)
    o.eligibility = Eligibility(EC.WORLDWIDE_REMOTE, 0.85, ["e"])
    return o


def test_pending_pool():
    first = lambda days: datetime.combine(TUESDAY - timedelta(days=days), datetime.min.time(), timezone.utc)  # noqa: E731
    assert in_pending_pool(_opp(Lifecycle.NEW), None, TUESDAY)
    assert in_pending_pool(_opp(Lifecycle.ACTIVE), first(10), TUESDAY)
    assert not in_pending_pool(_opp(Lifecycle.ACTIVE), first(20), TUESDAY)
    assert not in_pending_pool(_opp(Lifecycle.ACTIVE, notified_at=first(1)), first(10), TUESDAY)
    assert not in_pending_pool(_opp(Lifecycle.NEW, notified_at=first(1)), None, TUESDAY)


def test_gate_selects_a_pending_active_record():
    o = _opp(Lifecycle.ACTIVE)
    assert gate_reason(o, 0.0) == "not_new"
    assert gate_reason(o, 0.0, pending=True) is None


def test_urgent():
    stipend = _opp(Lifecycle.NEW)
    stipend.employment_type = ET.STIPEND_PROGRAM
    assert is_urgent(stipend, TUESDAY)
    soon, later = _opp(Lifecycle.NEW), _opp(Lifecycle.NEW)
    soon.deadline, later.deadline = TUESDAY + timedelta(days=14), TUESDAY + timedelta(days=15)
    assert is_urgent(soon, TUESDAY) and not is_urgent(later, TUESDAY) and not is_urgent(_opp(Lifecycle.NEW), TUESDAY)


# --- daily vs weekly --------------------------------------------------------------------------- #

def test_tuesday_delivers_only_urgent_and_defers_the_rest(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    s = run_once(cfg, _sources(TUESDAY), today=TUESDAY)
    md = _notify(tmp_path)
    assert s.notified == 1 and "Backend Intern A" in md and "Backend Intern B" not in md
    assert s.gate.get("deferred:weekly") == 2
    assert _check_invariant(s)
    assert list(_map(md)) == ["1"]
    title = (Path(tmp_path) / "notify_title.txt").read_text(encoding="utf-8")
    assert title == "Job Scout: 1 urgent — 2026-10-20"
    conn = connect(cfg.db_path)
    notified = {r["title"]: r["notified_at"] for r in conn.execute("SELECT title, notified_at FROM opportunities")}
    assert notified["Backend Intern A"] and notified["Backend Intern B"] is None and notified["Backend Intern C"] is None


def test_tuesday_with_nothing_urgent_writes_no_issue(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    run_once(cfg, [FakeSource("fake", [_intern("Backend Intern B")])], today=TUESDAY)
    assert _notify(tmp_path) == ""


def test_monday_delivers_all_numbered_with_map_and_funnel(tmp_path):
    cfg = _cfg(tmp_path)
    s = run_once(cfg, _sources(MONDAY), today=MONDAY)
    md = _notify(tmp_path)
    assert s.notified == 3 and _check_invariant(s)
    assert [int(n) for n in re.findall(r"^(\d+)\. \[", md, re.M)] == [1, 2, 3]
    m = _map(md)
    assert sorted(m) == ["1", "2", "3"] and len(set(m.values())) == 3
    assert "Reply with a comment such as: `apply 1,4 · maybe 2 · skip rest`" in md
    assert md.index("## Apply") < md.index("<details><summary>Weekly funnel</summary>") < md.index("</details>")
    title = (Path(tmp_path) / "notify_title.txt").read_text(encoding="utf-8")
    assert title == "Job Scout weekly — 3 new — 2026-10-26"


def test_monday_after_deferral_delivers_the_deferred_records(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    run_once(cfg, _sources(TUESDAY), today=TUESDAY)               # A delivered, B and C deferred
    s = run_once(cfg, _sources(TUESDAY), today=MONDAY)            # seen again unchanged → ACTIVE, still pending
    md = _notify(tmp_path)
    assert s.notified == 2 and "Backend Intern B" in md and "Backend Intern C" in md
    assert s.gate.get("already_notified") == 1


def test_monday_with_nothing_still_posts_the_funnel(tmp_path):
    cfg = _cfg(tmp_path)
    run_once(cfg, [FakeSource("empty", [])], today=MONDAY)
    md = _notify(tmp_path)
    assert "Weekly funnel" in md and _map(md) == {}
    assert (Path(tmp_path) / "notify_title.txt").read_text(encoding="utf-8") == "Job Scout weekly — 0 new — 2026-10-26"


def test_every_run_cadence_delivers_everything(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.notify.cadence = "every_run"
    s = run_once(cfg, _sources(TUESDAY), today=TUESDAY)
    assert s.notified == 3 and "deferred:weekly" not in s.gate


# --- item format ------------------------------------------------------------------------------- #

def test_item_format(tmp_path):
    run_once(_cfg(tmp_path), _sources(MONDAY), today=MONDAY)
    md = _notify(tmp_path)
    assert "1. [Backend Intern A](https://x.example/backend-intern-a) — Co Backend Intern A · internship" in md
    assert "    - **Eligibility:** worldwide_remote (" in md
    assert "matched:" not in md and "- [ ]" not in md


def test_heartbeat_near_misses_exclude_known_and_deferred():
    nm = [{"title": t, "company": "C", "location": "", "type": "internship", "eligibility": "", "score": 0.5,
           "gate_reason": r} for t, r in (("Kept", "role_family"), ("Dn", "already_notified"), ("Nn", "not_new"),
                                          ("Df", "deferred:weekly"))]
    rec = {"started": "2026-10-20T04:00", "discovered": 4, "after_filter": 4, "notified": 0, "near_misses": nm}
    md = render_heartbeat_md([rec])
    assert "Kept" in md and "| Dn |" not in md and "| Nn |" not in md and "| Df |" not in md


# --- 4.6 review findings ----------------------------------------------------------------------- #

def test_m1_failed_monday_digest_is_replayed_next_run(tmp_path):
    cfg = _cfg(tmp_path)
    run_once(cfg, _sources(MONDAY), today=MONDAY)
    Path(cfg.db_path).unlink()                                    # the issue step failed: state never committed
    s = run_once(cfg, _sources(MONDAY), today=MONDAY + timedelta(days=1))
    assert s.notified == 3 and "Weekly funnel" in _notify(tmp_path)


def test_l1_second_monday_run_posts_no_second_digest(tmp_path):
    cfg = _cfg(tmp_path)
    run_once(cfg, _sources(MONDAY), today=MONDAY)
    run_once(cfg, _sources(MONDAY), today=MONDAY)
    assert _notify(tmp_path) == ""


def test_m2_deferred_records_do_not_crowd_out_near_misses(tmp_path):
    cfg = _cfg(tmp_path)
    run_once(cfg, [FakeSource("empty", [])], today=MONDAY)
    miss = _intern("Sales Associate Intern")                     # a real miss: role_family
    opps = [_intern(f"Backend Intern {c}") for c in "BCDEFG"] + [miss]
    s = run_once(cfg, [FakeSource("fake", opps)], today=MONDAY + timedelta(days=1))
    assert s.gate.get("deferred:weekly") == 6
    assert [n["gate_reason"] for n in s.near_misses] == ["role_family"]


def test_l2_map_survives_a_key_containing_comment_end():
    from job_scout.notify import render_issue_md
    from job_scout.labels import item_map_of
    o = _opp(Lifecycle.NEW)
    o.ats_provider, o.ats_job_id = "himalayas", "https://h/x-->y"
    md = render_issue_md([o], AppConfig())
    map_line = next(ln for ln in md.splitlines() if ln.startswith("<!-- scout-items"))
    assert map_line.count("-->") == 1 and map_line.endswith(" -->")
    assert item_map_of(md) == {"1": "himalayas:https://h/x-->y"}
