"""Gate-0 fixtures — a hermetic FakeSource and the scenario opportunities the slice runs on.

No network, no model. Every fixture is a zero-arg factory returning a FRESH Opportunity, because
the pipeline mutates records in place (normalize, dedupe, scoring) — reusing a shared instance
across runs would leak state between tests. Named to make the Gate-0 assertions self-documenting.
"""

from __future__ import annotations

import copy

from job_scout.config import SourceConfig
from job_scout.models import EmploymentType, Opportunity, RemoteStatus


class FakeSource:
    """A Source that returns predefined Opportunities (fresh deep copies each fetch).

    `fail=True` simulates a TOTAL source failure (raises) so tests can prove the pipeline's
    per-source failure isolation. Returning an empty list instead means "genuinely nothing" — a
    deliberately different fact from a failure, per the Source protocol contract.
    """

    def __init__(self, name: str, opps: list[Opportunity] | None = None, *, fail: bool = False):
        self.name = name
        self._opps = opps or []
        self.fail = fail

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        if self.fail:
            raise RuntimeError(f"{self.name}: simulated total source failure")
        return [copy.deepcopy(o) for o in self._opps]


# --- individual scenario fixtures ------------------------------------------------------------- #


def stipend_opp() -> Opportunity:
    """STIPEND_PROGRAM_GLOBAL — structurally worldwide (should rank at the top tier)."""
    return Opportunity(
        title="Outreachy Internship — Open Source Contributor",
        company="Outreachy",
        apply_url="https://www.outreachy.org/apply/",
        canonical_url="",
        employment_type=EmploymentType.STIPEND_PROGRAM,
        description="A paid, fully remote internship contributing to open source. Worldwide, "
        "stipend of $5,500. Mentorship included. Great for Python beginners.",
        technologies=["python"],
    )


def worldwide_remote_opp() -> Opportunity:
    """WORLDWIDE_REMOTE — 'work from anywhere' (top eligibility tier)."""
    return Opportunity(
        title="Backend Engineering Intern",
        company="Zapier",
        apply_url="https://zapier.com/jobs/backend-intern",
        canonical_url="",
        description="Fully remote worldwide — work from anywhere. Build backend services in "
        "Python and SQL, containerized with Docker. Internship, entry level.",
        employment_type=EmploymentType.INTERNSHIP,
        technologies=["python", "sql", "docker"],
    )


def unknown_opp() -> Opportunity:
    """UNKNOWN eligibility — no location/authorization signal. The one the two above must outrank."""
    return Opportunity(
        title="Software Engineer Intern",
        company="Acme Corp",
        apply_url="https://acme.example.com/jobs/swe-intern",
        canonical_url="",
        description="Join our team building web services in Python. Internship for students.",
        employment_type=EmploymentType.INTERNSHIP,
        technologies=["python"],
    )


def work_auth_opp() -> Opportunity:
    """REQUIRES_WORK_AUTH at high confidence — a confident disqualifier (must be filtered out).

    Also carries a utm_source tracking param so the run exercises normalize.strip_tracking.
    """
    return Opportunity(
        title="Software Intern (US)",
        company="GovTech",
        apply_url="https://govtech.example.com/jobs/intern?utm_source=newsletter&gh_jid=99",
        canonical_url="",
        location_raw="Washington, DC, United States",
        description="Must be a US citizen. Requires an active security clearance. Onsite in DC.",
        employment_type=EmploymentType.INTERNSHIP,
        remote_status=RemoteStatus.ONSITE,
    )


def dup_greenhouse() -> Opportunity:
    """First-seen occurrence of the cross-source duplicate — the THINNER description."""
    return Opportunity(
        title="Data Engineer Intern",
        company="Globex",
        apply_url="https://boards.greenhouse.io/globex/jobs/123",
        canonical_url="",
        location_raw="Remote - EMEA",
        description="Data engineering internship at Globex.",
        employment_type=EmploymentType.INTERNSHIP,
        technologies=["python", "sql"],
    )


def dup_lever() -> Opportunity:
    """Second-seen occurrence of the SAME role from a different source — the RICHER description.

    Same company+title+location as `dup_greenhouse` → identical content fingerprint → they merge.
    Being the richer *second* occurrence, this is the regression case for the dedupe rework: its
    content must win and its provenance must survive in the merged record.
    """
    return Opportunity(
        title="Data Engineer Intern",
        company="Globex",
        apply_url="https://jobs.lever.co/globex/456",
        canonical_url="",
        location_raw="Remote - EMEA",
        description="A detailed Data Engineer Intern role at Globex: build and maintain data "
        "pipelines in Python and SQL, work with a distributed EMEA-remote team, and learn "
        "orchestration, warehousing, and testing. Open to candidates across EMEA.",
        employment_type=EmploymentType.INTERNSHIP,
        technologies=["python", "sql"],
    )


# --- assembled source set --------------------------------------------------------------------- #


def gate0_sources() -> list[FakeSource]:
    """The full Gate-0 source set: three live sources, one that fails (isolation), one cross-source
    duplicate split across two of them (greenhouse first so the richer lever copy is second)."""
    return [
        FakeSource("greenhouse", [dup_greenhouse(), work_auth_opp(), unknown_opp()]),
        FakeSource("lever", [dup_lever(), worldwide_remote_opp()]),
        FakeSource("programs", [stipend_opp()]),
        FakeSource("broken", fail=True),
    ]
