"""Known global programs — a CURATED source (not scraped). See PLAN.md §4.

For a user in Ethiopia the highest-value class of opportunity is the global open-source / fellowship
program: it is *structurally* worldwide (a stipend, not employment), so it bypasses work
authorization, EoR, and FX friction entirely. These are a small, slow-moving set of recurring
programs — so they are encoded here as data, with their application windows, rather than discovered.

Design:
  * Each program has one or more dated ROUNDS (application window + program period). A round is
    surfaced only when it is OPEN or opening within `LEAD_DAYS` (a heads-up), and never after its
    application deadline — the deadline is carried on the Opportunity so `hard_filter` also expires
    a round the instant it closes (belt and suspenders).
  * Dates are BEST-EFFORT approximations and say so, in the record itself, pointing at the official
    page for the authoritative dates. This source's job is a timely nudge to go check eligibility,
    not to be the system of record for deadlines. Refresh the round table each cycle.
  * `employment_type = STIPEND_PROGRAM`, so the pipeline's eligibility classifier returns
    `STIPEND_PROGRAM_GLOBAL` and ranks these at the top tier — which is the whole point.

The round table is the ONLY thing that needs periodic maintenance; the logic is date-driven and
deterministic (inject `today` to test any point in the cycle).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus

# How far before a round's application window opens we start surfacing it as a heads-up.
LEAD_DAYS = 45


@dataclass(frozen=True)
class _Round:
    key: str            # stable identity for this specific round (drives NEW/ACTIVE reconciliation)
    apply_opens: date
    apply_deadline: date
    period: str         # human note: the internship/coding period + stipend for THIS round


@dataclass(frozen=True)
class _Program:
    name: str
    org: str
    url: str
    stipend: str
    eligibility: str
    summary: str
    rounds: tuple[_Round, ...]


# --------------------------------------------------------------------------------------------- #
# The curated table. Dates are APPROXIMATE and flagged as such in every rendered record. Refresh
# each cycle from the official pages. (Verified facts live in STATE.md §Verified external facts.)
# --------------------------------------------------------------------------------------------- #

_PROGRAMS: tuple[_Program, ...] = (
    _Program(
        name="Outreachy Internship",
        org="Outreachy",
        url="https://www.outreachy.org/",
        stipend="~$5,500 USD (flat)",
        eligibility=(
            "worldwide incl. Ethiopia; 18+; ~30 hrs/week; INELIGIBLE if you have previously done "
            "Outreachy or Google Summer of Code"
        ),
        summary="Paid, fully remote internship contributing to free & open-source software, with mentorship.",
        rounds=(
            # Dec–Mar cohort: initial application window ~late-Jul → late-Aug.
            _Round("outreachy-2026-12", date(2026, 7, 29), date(2026, 8, 26),
                   "internship Dec 2026 – Mar 2027"),
            # May–Aug cohort: initial application window ~late-Jan → late-Feb.
            _Round("outreachy-2027-05", date(2027, 1, 27), date(2027, 2, 24),
                   "internship May 2027 – Aug 2027"),
        ),
    ),
    _Program(
        name="Google Summer of Code",
        org="Google Summer of Code",
        url="https://summerofcode.withgoogle.com/",
        stipend="~$3,000–$6,600 USD (PPP-adjusted by country)",
        eligibility=(
            "18+; all non-embargoed countries (Ethiopia eligible); fully remote; must be eligible "
            "to work in your country of residence (i.e. your own — no foreign work auth needed)"
        ),
        summary="Stipended remote contribution program pairing new contributors with open-source orgs.",
        rounds=(
            _Round("gsoc-2027", date(2027, 3, 24), date(2027, 4, 7),
                   "coding period May – Sep 2027"),
        ),
    ),
    _Program(
        name="MLH Fellowship",
        org="MLH Fellowship",
        url="https://fellowship.mlh.io/",
        stipend="stipend varies by batch/track",
        eligibility="worldwide, fully remote; ~12-week batches (Spring / Summer / Fall)",
        summary="Remote, collaborative software-engineering fellowship (Open Source / Software Eng tracks).",
        rounds=(
            _Round("mlh-2027-summer", date(2027, 2, 1), date(2027, 5, 1),
                   "Summer 2027 batch (~12 weeks, remote)"),
        ),
    ),
)


def _active_round(prog: _Program, today: date) -> _Round | None:
    """The earliest round that is open or opening within LEAD_DAYS and not past its deadline."""
    upcoming = sorted((r for r in prog.rounds if today <= r.apply_deadline), key=lambda r: r.apply_deadline)
    for r in upcoming:
        if today >= r.apply_opens - timedelta(days=LEAD_DAYS):
            return r
    return None


def _to_opportunity(prog: _Program, r: _Round, today: date) -> Opportunity:
    phase = "open now" if today >= r.apply_opens else "opening soon"
    title = f"{prog.name} — applications {phase} (deadline ~{r.apply_deadline:%b %d, %Y})"
    description = (
        f"{prog.summary} Stipend: {prog.stipend}. Eligibility: {prog.eligibility}. "
        f"Program period: {r.period}. Application window (APPROXIMATE — confirm the exact dates at "
        f"{prog.url}): opens ~{r.apply_opens:%b %d, %Y}, deadline ~{r.apply_deadline:%b %d, %Y}."
    )
    return Opportunity(
        title=title,
        company=prog.org,
        apply_url=prog.url,
        canonical_url="",                              # pipeline.normalize computes this
        ats_provider="known_programs",
        ats_job_id=r.key,                              # stable per-round identity
        remote_status=RemoteStatus.REMOTE,
        employment_type=EmploymentType.STIPEND_PROGRAM,
        description=description,
        deadline=r.apply_deadline,                     # expires the round the moment it closes
    )


class KnownProgramsSource:
    """A curated `Source`. Deterministic and offline: `today` is injectable for testing any point
    in the cycle; `programs` is injectable so tests are not coupled to the shipped table."""

    name = "known_programs"

    def __init__(self, today: date | None = None, programs: tuple[_Program, ...] = _PROGRAMS):
        self._today = today
        self._programs = programs

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        today = self._today or date.today()
        out: list[Opportunity] = []
        for prog in self._programs:
            r = _active_round(prog, today)
            if r is not None:
                out.append(_to_opportunity(prog, r, today))
        return out
