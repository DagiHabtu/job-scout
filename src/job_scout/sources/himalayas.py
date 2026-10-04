"""Himalayas remote-jobs search adapter (spec S7). Public, no auth, free.

Endpoint: `GET https://himalayas.app/jobs/api/search?<query>&sort=recent&page=N` → `{"jobs": [...],
"totalCount": n, "limit": 20, ...}`. Unlike company ATS boards, each listing carries a structured
`locationRestrictions` (empty = no restriction), `employmentType` and `seniority`, so location
eligibility comes from a field, not from prose.

Terms: Himalayas asks for a link back and attribution and forbids resubmitting listings to other job
platforms. The issue line for every Himalayas item links its Himalayas listing ("via Himalayas");
nothing is posted anywhere else. Rate limit: pages 1–3 per query, 1 s apart; a 429 stops that query.

Failure semantics (frozen `Source` contract): malformed listing → skip+log; one query failing →
logged, others continue; ALL queries failing → raise.
"""

from __future__ import annotations

import logging
import time
import urllib.error
from datetime import date, datetime, timezone

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus
from ._http import get_json
from ._text import html_to_text

log = logging.getLogger("job_scout.sources.himalayas")

_SEARCH_URL = "https://himalayas.app/jobs/api/search?{query}&sort=recent&page={page}"
_PAGES = 3
_PAUSE_S = 1.0


def _employment(job: dict) -> EmploymentType:
    etype = str(job.get("employmentType") or "")
    seniority = job.get("seniority") or []
    if etype == "Intern":
        return EmploymentType.INTERNSHIP
    if any("entry-level" in str(s).lower() for s in seniority):
        return EmploymentType.NEW_GRAD
    if etype == "Full Time":
        return EmploymentType.FULL_TIME
    if etype == "Contractor":
        return EmploymentType.CONTRACT
    return EmploymentType.UNKNOWN


def _epoch_date(value) -> date | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date() if value else None
    except (TypeError, ValueError, OSError):
        return None


def _to_opportunity(job: dict) -> Opportunity:
    title = str(job["title"]).strip()             # KeyError/None → malformed → skipped by caller
    guid = str(job["guid"]).strip()
    if not title or not guid:
        raise ValueError("empty title or guid")
    restrictions = [str(x).strip() for x in job.get("locationRestrictions") or [] if str(x).strip()]
    return Opportunity(
        title=title,
        company=str(job.get("companyName") or "").strip() or "Unknown",
        apply_url=str(job.get("applicationLink") or guid),
        canonical_url="",
        ats_provider="himalayas",
        ats_job_id=guid,                           # the Himalayas listing URL — linked as attribution
        location_raw="; ".join(restrictions) or "Worldwide",
        remote_status=RemoteStatus.REMOTE,
        employment_type=_employment(job),
        description=html_to_text(job.get("description") or job.get("excerpt") or ""),
        posting_date=_epoch_date(job.get("pubDate")),
        deadline=_epoch_date(job.get("expiryDate")),
    )


class HimalayasSource:
    """A `Source` over the Himalayas search API. `fetch_json` and `sleep` are injectable (tests)."""

    name = "himalayas"

    def __init__(self, queries: list[str] | None = None, *, fetch_json=get_json, sleep=time.sleep):
        self._queries = queries
        self._fetch_json = fetch_json
        self._sleep = sleep
        self.report: dict[str, str] = {}

    def _fetch_query(self, query: str) -> list[dict]:
        """Up to `_PAGES` pages. A 429 on a later page keeps what was fetched; on page 1 it fails."""
        jobs: list[dict] = []
        for page in range(1, _PAGES + 1):
            if page > 1:
                self._sleep(_PAUSE_S)
            try:
                data = self._fetch_json(_SEARCH_URL.format(query=query, page=page))
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    self.report[query] = f"rate_limited (HTTP 429 on page {page})"
                    log.warning("himalayas: 429 on %s page %d — stopping this query", query, page)
                    if page == 1:
                        raise
                    break
                raise
            batch = (data or {}).get("jobs") or []
            jobs.extend(batch)
            if len(batch) < int((data or {}).get("limit") or 20):
                break
        return jobs

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        self.skipped_records = 0                       # malformed records skipped (§6)
        queries = self._queries if self._queries is not None else list(cfg.himalayas_queries)
        self.report = {}
        if not queries:
            return []
        seen: set[str] = set()
        out: list[Opportunity] = []
        failures: list[str] = []
        for i, query in enumerate(queries):
            if i:
                self._sleep(_PAUSE_S)
            try:
                jobs = self._fetch_query(query)
            except Exception as exc:  # per-query isolation
                failures.append(query)
                log.warning("himalayas: query %s failed: %r", query, exc)
                continue
            for job in jobs:
                try:
                    opp = _to_opportunity(job)
                except Exception as exc:
                    log.warning("himalayas: skipping malformed listing: %r", exc)
                    self.skipped_records += 1
                    continue
                if opp.ats_job_id in seen:              # the four queries overlap
                    continue
                seen.add(opp.ats_job_id)
                out.append(opp)
            log.info("himalayas: %s → %d listings", query, len(jobs))
        if failures and len(failures) == len(queries):
            raise RuntimeError(f"himalayas: all {len(queries)} queries failed: {failures}")
        return out
