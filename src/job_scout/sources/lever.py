"""Lever postings adapter — Mode A (deep, company-scoped). See PLAN.md §4.

Endpoint (public, no auth, JSON): `GET api.lever.co/v0/postings/{site}?mode=json` → a JSON ARRAY of
postings. Unlike Greenhouse, Lever gives structured `categories` (location/commitment) and a
`workplaceType`, plus a ready-made `descriptionPlain`, so mapping is direct.

Documented gotcha: Lever intermittently returns an HTML page even with `mode=json`. `get_json`
raises on a non-JSON body, so that surfaces as a total failure for the site (isolated per-site) —
never mistaken for "this site has no jobs".

Failure semantics (frozen `Source` contract): malformed posting → skip+log; one site failing →
logged, others continue; ALL sites failing → raise.
"""

from __future__ import annotations

import logging

from ..config import SourceConfig
from ..models import EmploymentType, Opportunity, RemoteStatus
from ._http import get_json
from ._text import html_to_text

log = logging.getLogger("job_scout.sources.lever")

_POSTINGS_URL = "https://api.lever.co/v0/postings/{site}?mode=json"


def _prettify(slug: str) -> str:
    """Company display name from a Lever site slug ('some-co' → 'Some Co')."""
    return slug.replace("-", " ").replace("_", " ").strip().title() or slug


def _employment(commitment: str | None) -> EmploymentType:
    c = (commitment or "").lower()
    if "intern" in c:
        return EmploymentType.INTERNSHIP
    if "full" in c:
        return EmploymentType.FULL_TIME
    if "contract" in c or "temporary" in c or "temp" in c:
        return EmploymentType.CONTRACT
    return EmploymentType.UNKNOWN


def _remote(workplace: str | None) -> RemoteStatus:
    w = (workplace or "").lower()
    if w == "remote":
        return RemoteStatus.REMOTE
    if w in ("on-site", "onsite"):
        return RemoteStatus.ONSITE
    if w == "hybrid":
        return RemoteStatus.HYBRID
    return RemoteStatus.UNKNOWN  # "unspecified"/absent — let the pipeline infer from text


def _to_opportunity(posting: dict, company: str) -> Opportunity:
    """Map ONE Lever posting to an Opportunity, filling only fields Lever knows."""
    title = str(posting["text"]).strip()          # KeyError/None → malformed → skipped by caller
    if not title:
        raise ValueError("empty title")
    cats = posting.get("categories") or {}
    location = cats.get("location")
    plain = posting.get("descriptionPlain")
    description = html_to_text(plain if plain else (posting.get("description") or ""))
    return Opportunity(
        title=title,
        company=company,
        apply_url=str(posting.get("hostedUrl") or posting.get("applyUrl") or ""),
        canonical_url="",                          # pipeline.normalize computes this
        ats_provider="lever",
        ats_job_id=str(posting["id"]) if posting.get("id") else None,
        location_raw=location.strip() if isinstance(location, str) and location.strip() else None,
        remote_status=_remote(posting.get("workplaceType")),
        employment_type=_employment(cats.get("commitment")),
        description=description,
    )


class LeverSource:
    """A `Source` over one or more Lever site slugs.

    `sites` overrides the configured slugs (tests); when None, slugs come from `cfg.lever_sites`.
    `fetch_json` is the injectable HTTP layer (hermetic tests).
    """

    name = "lever"

    def __init__(self, sites: list[str] | None = None, *, fetch_json=get_json):
        self._sites = sites
        self._fetch_json = fetch_json

    def _fetch_site(self, site: str) -> list[Opportunity]:
        company = _prettify(site)
        data = self._fetch_json(_POSTINGS_URL.format(site=site))  # raises (incl. HTML) → site failure
        if not isinstance(data, list):
            raise RuntimeError(f"lever: expected a JSON array for site {site!r}, got {type(data).__name__}")
        opps: list[Opportunity] = []
        for posting in data:
            try:
                opps.append(_to_opportunity(posting, company))
            except Exception as exc:  # one malformed posting never aborts the site
                log.warning("lever: skipping malformed posting in site %s: %r", site, exc)
        log.info("lever: site %s → %d postings", site, len(opps))
        return opps

    def fetch(self, cfg: SourceConfig) -> list[Opportunity]:
        sites = self._sites if self._sites is not None else list(cfg.lever_sites)
        if not sites:
            log.info("lever: no sites configured")
            return []

        collected: list[Opportunity] = []
        failures: list[str] = []
        for site in sites:
            try:
                collected.extend(self._fetch_site(site))
            except Exception as exc:  # per-site isolation
                failures.append(site)
                log.warning("lever: site %s failed: %r", site, exc)

        if failures and len(failures) == len(sites):
            raise RuntimeError(f"lever: all {len(sites)} site(s) failed: {failures}")
        return collected
