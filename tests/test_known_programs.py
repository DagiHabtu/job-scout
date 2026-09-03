"""Known-programs curated source — date-driven surfacing + top-tier ranking through the pipeline."""

from __future__ import annotations

from datetime import date

from job_scout.config import AppConfig
from job_scout.models import EligibilityCategory as EC
from job_scout.models import Eligibility, EmploymentType, Lifecycle, Opportunity, Relevance
from job_scout.notify import select_for_notification
from job_scout.pipeline import run_once
from job_scout.sources.known_programs import (
    LEAD_DAYS,
    KnownProgramsSource,
    _Program,
    _Round,
    _active_round,
)


def _fetch(today):
    return KnownProgramsSource(today=today).fetch(cfg=None)


def _titles(today):
    return [o.company for o in _fetch(today)]


def test_round_is_surfaced_only_within_its_window():
    prog = _Program(
        name="Test", org="Test", url="https://x/", stipend="$1", eligibility="worldwide",
        summary="s",
        rounds=(_Round("r1", date(2027, 3, 1), date(2027, 4, 1), "period"),),
    )
    assert _active_round(prog, date(2027, 1, 1)) is None                 # too early (before lead)
    assert _active_round(prog, date(2027, 1, 15)).key == "r1"            # exactly LEAD_DAYS before opens
    assert _active_round(prog, date(2027, 3, 15)).key == "r1"            # open
    assert _active_round(prog, date(2027, 4, 1)).key == "r1"            # on the deadline (still in)
    assert _active_round(prog, date(2027, 4, 2)) is None                 # closed
    # LEAD_DAYS boundary is exact
    assert (date(2027, 3, 1) - date(2027, 1, 15)).days == LEAD_DAYS


def test_expired_round_is_skipped_for_the_next_one():
    prog = _Program(
        name="Two", org="Two", url="https://x/", stipend="$1", eligibility="worldwide", summary="s",
        rounds=(
            _Round("past", date(2026, 1, 1), date(2026, 2, 1), "old"),
            _Round("next", date(2027, 1, 1), date(2027, 2, 1), "new"),
        ),
    )
    assert _active_round(prog, date(2026, 12, 20)).key == "next"         # past one skipped


def test_outreachy_open_window_surfaces_as_stipend_program():
    # Mid-Feb 2027: the Outreachy May cohort application window is open.
    opps = _fetch(date(2027, 2, 10))
    outreachy = next((o for o in opps if o.company == "Outreachy"), None)
    assert outreachy is not None
    assert outreachy.employment_type == EmploymentType.STIPEND_PROGRAM
    assert outreachy.deadline == date(2027, 2, 24)
    assert outreachy.ats_provider == "known_programs" and outreachy.ats_job_id == "outreachy-2027-05"
    assert "open now" in outreachy.title.lower()
    assert "approximate" in outreachy.description.lower()               # honesty about dates


def test_opening_soon_phrasing_before_open_date():
    # Late Feb 2027 is within GSoC's lead window but before its open date.
    opps = _fetch(date(2027, 2, 20))
    gsoc = next((o for o in opps if o.company == "Google Summer of Code"), None)
    assert gsoc is not None and "opening soon" in gsoc.title.lower()


def test_quiet_period_surfaces_nothing_today_dates():
    # Early Sep 2026: the Dec cohort's application window has closed and the next windows are >LEAD
    # away — an honest empty result rather than a stale/misleading one.
    assert _fetch(date(2026, 9, 3)) == []


def test_best_fit_stipend_surfaces_below_threshold_but_unknown_does_not():
    def mk(cat):
        o = Opportunity(title="P", company="C", apply_url="u", canonical_url="u", status=Lifecycle.NEW)
        o.eligibility = Eligibility(cat, 0.9)
        o.relevance = Relevance(score=0.10)          # well below any sane threshold
        return o

    stipend = mk(EC.STIPEND_PROGRAM_GLOBAL)
    unknown = mk(EC.UNKNOWN)
    picked = select_for_notification([stipend, unknown], threshold=0.45)
    assert stipend in picked                          # best-fit class surfaces on eligibility alone
    assert unknown not in picked                      # a low-relevance UNKNOWN does not


def test_program_ranks_top_tier_and_notifies_through_the_pipeline(tmp_path):
    cfg = AppConfig()
    cfg.db_path = str(tmp_path / "scout.db")
    cfg.notify.digest_path = str(tmp_path / "digest.html")
    today = date(2027, 2, 10)

    summary = run_once(cfg, [KnownProgramsSource(today=today)], today=today)
    assert summary.sources["known_programs"]["ok"] is True
    assert summary.ranked, "expected at least one program surfaced"

    top = summary.ranked[0]
    assert top.eligibility.category == EC.STIPEND_PROGRAM_GLOBAL     # structurally worldwide → top tier
    assert top.status == Lifecycle.NEW
    assert summary.notified >= 1                                     # a stipend program is worth surfacing

    # idempotency: a second run marks them ACTIVE and does not re-notify
    summary2 = run_once(cfg, [KnownProgramsSource(today=today)], today=today)
    assert summary2.lifecycle["new"] == 0 and summary2.notified == 0
