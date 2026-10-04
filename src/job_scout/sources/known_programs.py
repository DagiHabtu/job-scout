"""Known global programs — a CURATED calendar (not scraped). See PLAN.md §4 and spec S6.

Nothing is fetched at run time. Each program carries its own geographic rule — a verbatim quote, the
URL it came from, and the date it was checked — plus the personal conditions the system cannot
check. Each round carries its state (`open` / `announced` / `expected`) with its own source URL and
check date. Every emitted record says how sure it is:

  * eligibility comes from `geo_verdict` (the program's own rule, never "stipend ⇒ worldwide");
  * a round is announced once per state (`ats_job_id = "<round>@<state>"`), so a heads-up while
    `expected` does not suppress the "now open" notice;
  * a stale check degrades: an open/announced round checked >45 days ago is treated as expected, a
    geographic rule checked >365 days ago makes the verdict "unknown";
  * rounds and programs that emit nothing say why in `KnownProgramsSource.report`.

Maintenance: `TABLE_VERIFIED_ON`; the weekly heartbeat lists everything due for a re-check
(`maintenance_notes`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus

TABLE_VERIFIED_ON = date(2026, 10, 4)

LEAD_ANNOUNCED = 30          # days before apply_opens that an announced round is surfaced
LEAD_EXPECTED = 51           # extrapolated dates need slack (Outreachy's last window was 7 days)
STALE_STATE_DAYS = 45        # an open/announced state older than this is treated as expected
STALE_GEO_DAYS = 365         # a geographic rule older than this gives verdict "unknown"
RECHECK_DAYS = 30            # heartbeat asks for a re-check after this

# Countries/regions under comprehensive U.S. embargo, for programs whose rule is "not residing in a
# U.S.-embargoed country". Checked 2026-10-04 against OFAC's active program list: comprehensive
# programs Cuba, Iran, North Korea and the Crimea / so-called DNR / LNR regions; Syria's program is
# now the targeted PAARSS program; no Ethiopia-related program is active.
US_EMBARGOED: frozenset[str] = frozenset({"cuba", "iran", "north korea", "crimea", "donetsk", "luhansk"})
US_EMBARGOED_URL = "https://ofac.treasury.gov/sanctions-programs-and-country-information"
US_EMBARGOED_CHECKED_ON: date | None = date(2026, 10, 4)     # None = not verified → embargo-rule programs "unknown"

State = Literal["open", "announced", "expected"]


@dataclass(frozen=True)
class _Round:
    key: str            # stable identity for this round
    apply_opens: date
    apply_deadline: date
    period: str         # human note: the program period for THIS round
    state: State
    state_url: str
    state_checked_on: date


@dataclass(frozen=True)
class _Program:
    name: str
    org: str
    url: str
    stipend: str
    summary: str
    rounds: tuple[_Round, ...]
    geo_scope: Literal["worldwide", "unknown"]
    geo_quote: str                       # the program's own rule, verbatim
    geo_url: str
    geo_checked_on: date
    geo_exclusions: tuple[str, ...] = ()  # places the program itself excludes / has no projects
    embargo_rule: bool = False            # rule is "not residing in a U.S.-embargoed country"
    conditions: tuple[str, ...] = ()      # personal requirements the system cannot check


_PROGRAMS: tuple[_Program, ...] = (
    _Program(
        name="Outreachy Internship",
        org="Outreachy",
        url="https://www.outreachy.org/",
        stipend="$7,000 USD",
        summary="Paid, fully remote internship contributing to free & open-source software, with mentorship.",
        geo_scope="worldwide",
        geo_quote="Outreachy is open to applicants around the world.",
        geo_url="https://www.outreachy.org/docs/applicant/",
        geo_checked_on=date(2026, 10, 4),
        conditions=(
            "30 hours/week",
            "university students need 42 consecutive days free from school and exams during the internship",
            "students in the Northern Hemisphere may apply only to the May–August cohort",
        ),
        # No December rounds: Ethiopia is in the Northern Hemisphere, so for a university student
        # that cohort is excluded by Outreachy's own rule.
        rounds=(
            _Round("outreachy-2027-05", date(2027, 2, 5), date(2027, 2, 12), "internship May – Aug 2027",
                   "expected", "https://www.outreachy.org/", date(2026, 10, 4)),
        ),
    ),
    _Program(
        name="Google Summer of Code",
        org="Google Summer of Code",
        url="https://summerofcode.withgoogle.com/",
        stipend="$3,000–$6,600 USD (PPP-adjusted by country)",
        summary="Stipended remote contribution program pairing new contributors with open-source orgs.",
        geo_scope="worldwide",
        geo_quote="Not residing in a U.S. embargoed country",
        geo_url="https://developers.google.com/open-source/gsoc/faq",
        geo_checked_on=date(2026, 10, 4),
        embargo_rule=True,
        conditions=(
            "18+ years old at registration",
            "eligible to work in your country of residence",
            "student or open source beginner",
            "accepted into GSoC no more than once previously",
        ),
        rounds=(
            _Round("gsoc-2027", date(2027, 3, 24), date(2027, 4, 7), "coding period May – Sep 2027",
                   "expected", "https://developers.google.com/open-source/gsoc/timeline", date(2026, 10, 4)),
        ),
    ),
    _Program(
        name="LFX Mentorship",
        org="Linux Foundation",
        url="https://mentorship.lfx.linuxfoundation.org/",
        stipend="stipend varies by program",
        summary="Linux Foundation open-source mentorships, three full-time terms a year.",
        # The rule does not state worldwide eligibility explicitly → "unknown" (spec S6).
        geo_scope="unknown",
        geo_quote=(
            "Be eligible to work in the country and jurisdiction where you will be participating in the "
            "Mentorship program. Not reside in a country or jurisdiction where participation in the mentorship "
            "is prohibited under applicable U.S. federal, state or local laws or the laws of other countries"
        ),
        geo_url="https://docs.linuxfoundation.org/lfx/mentorship/mentee-guide/am-i-eligible",
        geo_checked_on=date(2026, 10, 4),
        conditions=("18+ by the time the mentorship starts", "not a prior or active Linux Foundation mentee"),
        rounds=tuple(
            _Round(key, opens, deadline, period, "expected",
                   "https://docs.linuxfoundation.org/lfx/mentorship/mentorship-program-timelines", date(2026, 10, 4))
            for key, opens, deadline, period in (
                ("lfx-2027-spring", date(2027, 1, 15), date(2027, 2, 12), "Spring term Mar 1 – May 31, 2027"),
                ("lfx-2027-summer", date(2027, 4, 15), date(2027, 5, 13), "Summer term Jun 1 – Aug 31, 2027"),
                ("lfx-2027-fall", date(2027, 7, 15), date(2027, 8, 12), "Fall term Sep 1 – Nov 30, 2027"),
            )
        ),
    ),
    _Program(
        name="MLH Fellowship",
        org="MLH Fellowship",
        url="https://fellowship.mlh.com/",
        stipend="stipend varies by batch/track",
        summary="Remote, collaborative software-engineering fellowship.",
        # The form's list of countries with no anticipated projects was not extracted, so the
        # exclusions are unverified → "unknown". No round: Fall 2026 closed 2026-08-31 and no later
        # batch is published; add one only when the official form shows it.
        geo_scope="unknown",
        geo_quote="Residency: I do not reside in a country embargoed by the United States.",
        geo_url="https://www.tfaforms.com/4956119",
        geo_checked_on=date(2026, 10, 4),
        embargo_rule=True,
        conditions=(
            "must have participated in at least one MLH Hackathon or Global Hack Week event",
            "20 hours/week",
            "30 Mbps internet",
            "the Production Engineering track is US/Canada/Mexico only",
        ),
        rounds=(),
    ),
)

# round key → (program, the `today` of the fetch that emitted it). Lets the eligibility stage, which
# only sees `ats_job_id`, find the program — including injected test programs.
_INDEX: dict[str, tuple[_Program, date]] = {}


def _index(programs: tuple[_Program, ...], today: date) -> None:
    for p in programs:
        for r in p.rounds:
            _INDEX[r.key] = (p, today)


def _lookup(ats_job_id: str | None) -> tuple[_Program, date] | None:
    if not ats_job_id:
        return None
    key = ats_job_id.split("@", 1)[0]
    if key not in _INDEX:
        _index(_PROGRAMS, date.today())
    return _INDEX.get(key)


def geo_verdict(ats_job_id: str | None, country: str) -> str:
    """Geographic eligibility of a program round for `country`: "eligible" | "excluded" | "unknown".

    "excluded" when the program itself excludes `country`, or its rule is the U.S.-embargo rule and
    `country` is embargoed; "eligible" only when the program states a worldwide rule, the check is
    fresh, and (for embargo-rule programs) the embargo list was verified; otherwise "unknown".
    """
    found = _lookup(ats_job_id)
    if found is None:
        return "unknown"
    p, today = found
    c = country.strip().lower()
    if c in {x.lower() for x in p.geo_exclusions}:
        return "excluded"
    if p.embargo_rule:
        if US_EMBARGOED_CHECKED_ON is None:
            return "unknown"
        if c in US_EMBARGOED:
            return "excluded"
    if p.geo_scope == "worldwide" and (today - p.geo_checked_on).days <= STALE_GEO_DAYS:
        return "eligible"
    return "unknown"


def geo_evidence(ats_job_id: str | None) -> list[str]:
    """The program's quoted rule, URL and check date, plus every condition the system cannot check."""
    found = _lookup(ats_job_id)
    if found is None:
        return []
    p, _ = found
    ev = [f'program rule: "{p.geo_quote}"', f"source: {p.geo_url} (checked {p.geo_checked_on.isoformat()})"]
    if p.embargo_rule and US_EMBARGOED_CHECKED_ON:
        ev.append(f"U.S. embargo list checked {US_EMBARGOED_CHECKED_ON.isoformat()} ({US_EMBARGOED_URL})")
    ev += [f"condition (not checked): {c}" for c in p.conditions]
    return ev


def effective_state(r: _Round, today: date) -> State:
    if r.state in ("open", "announced") and (today - r.state_checked_on).days > STALE_STATE_DAYS:
        return "expected"
    return r.state


def _emitted(r: _Round, today: date) -> tuple[bool, str]:
    """(emit?, reason if not). Emitted iff not past its deadline and open or within its lead window."""
    if today > r.apply_deadline:
        return False, "deadline_passed"
    state = effective_state(r, today)
    lead = LEAD_ANNOUNCED if state == "announced" else LEAD_EXPECTED
    if state == "open" or today >= r.apply_opens - timedelta(days=lead):
        return True, ""
    return False, "outside_lead_window"


def _fmt(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _to_opportunity(p: _Program, r: _Round, today: date) -> Opportunity:
    state = effective_state(r, today)
    if state == "open":
        title = f"{p.name} — applications open (deadline {_fmt(r.apply_deadline)})"
    elif state == "announced":
        title = f"{p.name} — opens {_fmt(r.apply_opens)}"
    else:
        title = (f"{p.name} — expected around {r.apply_opens:%b %Y} "
                 f"(dates not published; last checked {r.state_checked_on.isoformat()})")
    conditions = "; ".join(p.conditions) or "none listed"
    description = (
        f"{p.summary} Stipend: {p.stipend}. Program period: {r.period}. "
        f"Application window ({state}; source {r.state_url}, checked {r.state_checked_on.isoformat()}): "
        f"opens {_fmt(r.apply_opens)}, deadline {_fmt(r.apply_deadline)}. "
        f'Geographic rule: "{p.geo_quote}" ({p.geo_url}, checked {p.geo_checked_on.isoformat()}). '
        f"Conditions you must check yourself: {conditions}."
    )
    return Opportunity(
        title=title,
        company=p.org,
        apply_url=p.url,
        canonical_url="",                              # pipeline.normalize computes this
        ats_provider="known_programs",
        ats_job_id=f"{r.key}@{state}",                 # one announcement per state
        remote_status=RemoteStatus.REMOTE,
        employment_type=EmploymentType.STIPEND_PROGRAM,
        description=description,
        deadline=r.apply_deadline,
    )


def validate_table(programs: tuple[_Program, ...]) -> list[str]:
    """Problems that make the table untrustworthy (empty list = OK)."""
    problems: list[str] = []
    for p in programs:
        if p.geo_scope not in ("worldwide", "unknown"):
            problems.append(f"{p.name}: bad geo_scope {p.geo_scope!r}")
        if p.geo_scope == "worldwide" and not (p.geo_quote and p.geo_url and p.geo_checked_on):
            problems.append(f"{p.name}: worldwide without quote/url/check date")
        for r in p.rounds:
            if r.state not in ("open", "announced", "expected"):
                problems.append(f"{r.key}: bad state {r.state!r}")
            if not (r.state_url and r.state_checked_on):
                problems.append(f"{r.key}: missing state_url/state_checked_on")
            if r.apply_opens > r.apply_deadline:
                problems.append(f"{r.key}: opens after its deadline")
    return problems


def maintenance_notes(today: date, programs: tuple[_Program, ...] = _PROGRAMS) -> list[str]:
    """Heartbeat lines: every stale check ("re-check: <url>") and every program with no future round."""
    notes: list[str] = []
    for p in programs:
        if (today - p.geo_checked_on).days > RECHECK_DAYS:
            notes.append(f"- re-check: {p.geo_url} ({p.name} geographic rule, last checked {p.geo_checked_on})")
        for r in p.rounds:
            if today <= r.apply_deadline and (today - r.state_checked_on).days > RECHECK_DAYS:
                notes.append(f"- re-check: {r.state_url} ({r.key} dates, last checked {r.state_checked_on})")
        if not any(today <= r.apply_deadline for r in p.rounds):
            notes.append(f"- {p.name}: no_published_round — check {p.url}")
    return (["**Programs calendar maintenance**", ""] + notes) if notes else []


class KnownProgramsSource:
    """A curated `Source`. Deterministic and offline: `today` and `programs` are injectable."""

    name = "known_programs"

    def __init__(self, today: date | None = None, programs: tuple[_Program, ...] = _PROGRAMS):
        self._today = today
        self._programs = programs
        self.report: dict[str, str] = {}

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        today = self._today or date.today()
        _index(self._programs, today)
        self.report = {}
        out: list[Opportunity] = []
        for p in self._programs:
            for r in p.rounds:
                ok, why = _emitted(r, today)
                if ok:
                    out.append(_to_opportunity(p, r, today))
                else:
                    self.report[r.key] = why
            if not any(today <= r.apply_deadline for r in p.rounds):
                last = max([p.geo_checked_on, *(r.state_checked_on for r in p.rounds)])
                self.report[p.name] = f"no_published_round (last checked {last.isoformat()})"
        return out
