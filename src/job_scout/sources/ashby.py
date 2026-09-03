"""Ashby job-board adapter — Mode A (deep, company-scoped). See PLAN.md §4.

Endpoint (public, no auth, JSON): `GET api.ashbyhq.com/posting-api/job-board/{org}` → `{"jobs":[...]}`.
Ashby gives structured fields (`employmentType`, `workplaceType`/`isRemote`, `location`) and a
ready-made `descriptionPlain`, plus an `isListed` flag for jobs that should be shown publicly.

Failure semantics (frozen `Source` contract): malformed job → skip+log; one org failing → logged,
others continue; ALL orgs failing → raise (a genuine total failure the pipeline isolates).
"""

from __future__ import annotations

import logging

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus
from ._http import get_json
from ._text import html_to_text

log = logging.getLogger("job_scout.sources.ashby")

_BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"


def _prettify(org: str) -> str:
    return org.replace("-", " ").replace("_", " ").strip().title() or org


def _employment(value: str | None) -> EmploymentType:
    v = (value or "").lower()
    if "intern" in v:
        return EmploymentType.INTERNSHIP
    if "full" in v:
        return EmploymentType.FULL_TIME
    if "contract" in v or "temp" in v:
        return EmploymentType.CONTRACT
    return EmploymentType.UNKNOWN


def _remote(job: dict) -> RemoteStatus:
    w = str(job.get("workplaceType") or "").lower()
    if "remote" in w:
        return RemoteStatus.REMOTE
    if "hybrid" in w:
        return RemoteStatus.HYBRID
    if w in ("onsite", "inperson", "in-person", "in office", "inoffice"):
        return RemoteStatus.ONSITE
    if job.get("isRemote") is True:
        return RemoteStatus.REMOTE
    return RemoteStatus.UNKNOWN  # let the pipeline infer from text


def _to_opportunity(job: dict, company: str) -> Opportunity:
    """Map ONE Ashby job to an Opportunity, filling only fields Ashby knows."""
    title = str(job["title"]).strip()             # KeyError/None → malformed → skipped by caller
    if not title:
        raise ValueError("empty title")
    location = job.get("location")
    plain = job.get("descriptionPlain")
    description = html_to_text(plain if plain else (job.get("descriptionHtml") or ""))
    return Opportunity(
        title=title,
        company=company,
        apply_url=str(job.get("jobUrl") or job.get("applyUrl") or ""),
        canonical_url="",                          # pipeline.normalize computes this
        ats_provider="ashby",
        ats_job_id=str(job["id"]) if job.get("id") else None,
        location_raw=location.strip() if isinstance(location, str) and location.strip() else None,
        remote_status=_remote(job),
        employment_type=_employment(job.get("employmentType")),
        description=description,
    )


class AshbySource:
    """A `Source` over one or more Ashby org slugs. `orgs` overrides `cfg.ashby_orgs` (tests);
    `fetch_json` is the injectable HTTP layer."""

    name = "ashby"

    def __init__(self, orgs: list[str] | None = None, *, fetch_json=get_json):
        self._orgs = orgs
        self._fetch_json = fetch_json

    def _fetch_org(self, org: str) -> list[Opportunity]:
        company = _prettify(org)
        data = self._fetch_json(_BOARD_URL.format(org=org))       # raises → org-level failure
        jobs = (data or {}).get("jobs") or []
        opps: list[Opportunity] = []
        for job in jobs:
            if job.get("isListed") is False:                       # respect Ashby's public-listing flag
                continue
            try:
                opps.append(_to_opportunity(job, company))
            except Exception as exc:  # one malformed job never aborts the org
                log.warning("ashby: skipping malformed job in org %s: %r", org, exc)
        log.info("ashby: org %s → %d jobs", org, len(opps))
        return opps

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        orgs = self._orgs if self._orgs is not None else list(cfg.ashby_orgs)
        if not orgs:
            log.info("ashby: no orgs configured")
            return []

        collected: list[Opportunity] = []
        failures: list[str] = []
        for org in orgs:
            try:
                collected.extend(self._fetch_org(org))
            except Exception as exc:  # per-org isolation
                failures.append(org)
                log.warning("ashby: org %s failed: %r", org, exc)

        if failures and len(failures) == len(orgs):
            raise RuntimeError(f"ashby: all {len(orgs)} org(s) failed: {failures}")
        return collected
