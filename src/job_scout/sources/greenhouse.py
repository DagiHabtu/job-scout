"""Greenhouse job-board adapter — Mode A (deep, company-scoped, high quality). See PLAN.md §4.

Endpoint (public, no auth, JSON): `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`.
`content=true` returns the full description (HTML, entity-encoded) so the scorer/eligibility have real
text. The board's display name comes from `GET /v1/boards/{token}` (best-effort enrichment).

Dependency-light on purpose: stdlib `urllib` + `json` only — no `requests`, no HTML parser. The HTTP
layer is injected (`fetch_json`) so tests run hermetically against a recorded fixture.

Failure semantics (frozen `Source` contract):
  * one malformed job record → skip + log (never aborts the board);
  * one board failing (bad token, 404) → logged, other boards continue;
  * ALL boards failing (network down, every token bad) → raise (a genuine total failure the
    pipeline isolates) — never swallowed into an empty list, which would mean "genuinely nothing".
"""

from __future__ import annotations

import logging

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus
from ._http import get_json
from ._text import html_to_text as _html_to_text  # re-exported for tests

log = logging.getLogger("job_scout.sources.greenhouse")

_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
_BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{token}"


def _prettify(token: str) -> str:
    """Fallback company name from a board token when board metadata is unavailable ('gitlab' → 'Gitlab')."""
    return token.replace("-", " ").replace("_", " ").strip().title() or token


def _to_opportunity(job: dict, company: str) -> Opportunity:
    """Map ONE Greenhouse job record to an Opportunity, filling only fields Greenhouse knows.

    Derived fields (canonical_url, remote_status inference, content_fingerprint, eligibility,
    relevance) are intentionally left to the pipeline. A missing title makes the record malformed
    (caller skips it); everything else degrades to an honest null/UNKNOWN.
    """
    title = str(job["title"]).strip()            # KeyError/None → malformed → skipped by caller
    if not title:
        raise ValueError("empty title")
    job_id = job.get("id") if job.get("id") is not None else job.get("internal_job_id")
    location = (job.get("location") or {}).get("name")
    return Opportunity(
        title=title,
        company=company,
        apply_url=str(job.get("absolute_url") or ""),
        canonical_url="",                         # pipeline.normalize computes this
        ats_provider="greenhouse",
        ats_job_id=str(job_id) if job_id is not None else None,
        location_raw=location.strip() if isinstance(location, str) and location.strip() else None,
        remote_status=RemoteStatus.UNKNOWN,       # inferred downstream from text
        employment_type=EmploymentType.UNKNOWN,   # Greenhouse board API does not classify this
        description=_html_to_text(job.get("content") or ""),
    )


class GreenhouseSource:
    """A `Source` over one or more Greenhouse board tokens.

    `boards` overrides the configured tokens (used in tests); when None, tokens come from
    `cfg.greenhouse_boards`. `fetch_json` is the injectable HTTP layer (hermetic tests).
    """

    name = "greenhouse"

    def __init__(self, boards: list[str] | None = None, *, fetch_json=get_json):
        self._boards = boards
        self._fetch_json = fetch_json

    def _board_company(self, token: str) -> str:
        """Best-effort real company name from board metadata; never raises (enrichment only)."""
        try:
            meta = self._fetch_json(_BOARD_URL.format(token=token))
            name = str((meta or {}).get("name") or "").strip()
            return name or _prettify(token)
        except Exception as exc:  # metadata is optional — degrade, do not fail the board
            log.debug("greenhouse: no board metadata for %s (%r); using token", token, exc)
            return _prettify(token)

    def _fetch_board(self, token: str) -> list[Opportunity]:
        company = self._board_company(token)
        data = self._fetch_json(_JOBS_URL.format(token=token))  # raises → board-level failure
        jobs = (data or {}).get("jobs") or []
        opps: list[Opportunity] = []
        for job in jobs:
            try:
                opps.append(_to_opportunity(job, company))
            except Exception as exc:  # one malformed record never aborts the board
                log.warning("greenhouse: skipping malformed job in board %s: %r", token, exc)
        log.info("greenhouse: board %s → %d jobs", token, len(opps))
        return opps

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        boards = self._boards if self._boards is not None else list(cfg.greenhouse_boards)
        if not boards:
            log.info("greenhouse: no boards configured")
            return []

        collected: list[Opportunity] = []
        failures: list[str] = []
        for token in boards:
            try:
                collected.extend(self._fetch_board(token))
            except Exception as exc:  # per-board isolation
                failures.append(token)
                log.warning("greenhouse: board %s failed: %r", token, exc)

        # Every board failing is a genuine total source failure — raise so the pipeline records it
        # as a failure (drives gone-detection), rather than reporting a misleading empty result.
        if failures and len(failures) == len(boards):
            raise RuntimeError(f"greenhouse: all {len(boards)} board(s) failed: {failures}")
        return collected
