"""Deterministic eligibility classification — $0, no ML, no network.

Answers: *can the user, at their configured location, realistically apply for this?* The honest
default is uncertainty — most postings do not state their geographic/authorization scope — so the
result is `{category, confidence, evidence}`, `UNKNOWN` is first-class, and only a CONFIDENT
disqualifier (work-auth-required, remote-excludes-user, onsite-foreign) removes an opportunity. A
degrade in confidence is surfaced, never silently applied.

This is a signal extractor over posting text; it is intentionally conservative (favouring UNKNOWN
over a wrong confident call). An optional local LLM can later refine the UNKNOWN bucket, but this
must stand alone at $0.
"""

from __future__ import annotations

import re

from .config import UserProfile
from .models import Eligibility, EligibilityCategory, EmploymentType, Opportunity, RemoteStatus

# --------------------------------------------------------------------------------------------- #
# Pattern vocabulary. Short tokens (us, uk, eu) use word boundaries to avoid matching inside other
# words ("queue", "bus"); phrases use plain substring. All matching is lowercase.
# --------------------------------------------------------------------------------------------- #

# Global open-source / fellowship programs that are structurally worldwide (stipend, not employment).
_STIPEND_PROGRAMS = (
    "outreachy",
    "google summer of code",
    "gsoc",
    "mlh fellowship",
    "major league hacking fellowship",
    "season of docs",
    "linux foundation mentorship",
    "summer of bitcoin",
)

# Regions/scopes that INCLUDE Ethiopia (Africa).
_INCLUDES_AFRICA = ("africa", "emea", "worldwide", "world wide", "global", "anywhere", "any country", "any location", "any timezone")

# The user's own location tokens (built per-profile at call time, plus these regional aliases).
_EAST_AFRICA = ("east africa", "eastern africa", " eat ", "gmt+3", "utc+3", "central africa time", " cat ")

# Restrictive scopes that EXCLUDE Ethiopia when named as the allowed region. Note EMEA is NOT here
# (it includes Africa); "europe"/"eu"/"eea" ARE (Ethiopia is not in Europe).
_EXCLUDES_ET = (
    "united states",
    "u.s.",
    "us only",
    "us-based",
    "us based",
    "based in the us",
    "within the us",
    "canada",
    "united kingdom",
    "uk only",
    "great britain",
    "european union",
    "eu only",
    "eea",
    "europe only",
    "latam",
    "apac",
    "north america",
    "australia",
)
_EXCLUDES_ET_TOKENS = (r"\bus\b", r"\buk\b", r"\beu\b")  # bare country tokens, boundary-guarded

# Foreign work-authorization requirements (disqualifying for an ET-resident without that auth).
_WORK_AUTH = (
    "authorized to work in",
    "authorization to work in",
    "right to work in",
    "must be a us citizen",
    "u.s. citizen",
    "us citizenship",
    "green card",
    "security clearance",
    "requires clearance",
    "no visa sponsorship",
    "not sponsor",
    "will not sponsor",
    "unable to sponsor",
    "without sponsorship",
    "must reside in the",
    "must be located in the",
    "must be based in",
)
# GSoC-style benign phrasing that is NOT a foreign-auth requirement.
_BENIGN_AUTH = ("your country of residence", "in your country", "country you reside")

# US-hours requirements — a practical (not legal) obstacle from UTC+3; EU-hours is fine for ET.
_US_HOURS = ("pacific time", "pst", "pdt", "eastern time", " est ", " edt ", "us business hours", "overlap with us")
_EU_HOURS = ("central european", " cet ", " cest ", "european hours", "overlap with european", "gmt+1", "gmt+2")

_WORLDWIDE = ("work from anywhere", "fully remote worldwide", "remote worldwide", "remote - global", "remote, global", "no location requirement", "location independent")


def _has(hay: str, needles) -> bool:
    return any(n in hay for n in needles)


def _has_token(hay: str, patterns) -> bool:
    return any(re.search(p, hay) for p in patterns)


def classify_eligibility(opp: Opportunity, profile: UserProfile) -> Eligibility:
    """Return an honest eligibility judgement for `opp` given the user's `profile`.

    Priority order (first decisive signal wins), then positive signals, then UNKNOWN. A US-hours
    requirement is folded in as a confidence penalty / concern rather than a hard category, because
    it is a practical obstacle, not a legal one.
    """
    hay = f" {opp.title} {opp.description} {opp.location_raw or ''} ".lower()
    ev: list[str] = []

    own_country = profile.location.country_name.lower()
    own_code = profile.location.country_code.lower()
    own_city = (profile.location.city or "").lower()
    authed = {c.lower() for c in profile.work_authorization}

    # 1) Global stipend program — structurally worldwide (Ethiopia is not US-embargoed).
    if opp.employment_type == EmploymentType.STIPEND_PROGRAM or _has(hay, _STIPEND_PROGRAMS):
        hit = next((p for p in _STIPEND_PROGRAMS if p in hay), "stipend program")
        ev.append(f"global open program ({hit}): worldwide, stipend not employment")
        return Eligibility(EligibilityCategory.STIPEND_PROGRAM_GLOBAL, 0.9, ev)

    # 2) Foreign work authorization required (unless the benign 'your country of residence' phrasing).
    if _has(hay, _WORK_AUTH) and not _has(hay, _BENIGN_AUTH):
        # If it explicitly requires auth in a country the user already has, it is not disqualifying.
        # The country code is matched on a word boundary — a bare substring test lets a 2-letter code
        # like "et" match inside ordinary words ("meetings", "get") and silently mask a real
        # foreign-auth requirement. The country NAME stays a plain substring (it is distinctive).
        owns_named = own_country in hay or re.search(rf"\b{re.escape(own_code)}\b", hay) is not None
        requires_owned = own_code in authed and owns_named
        if not requires_owned:
            hit = next((p for p in _WORK_AUTH if p in hay), "work authorization")
            ev.append(f"requires work authorization the user lacks ('{hit}')")
            return Eligibility(EligibilityCategory.REQUIRES_WORK_AUTH, 0.85, ev)

    # 2b) The structured LOCATION field is authoritative over free-text boilerplate. Large all-remote
    #     employers repeat generic "global / work-from-anywhere" language in every description; that
    #     must NOT rescue a role whose location explicitly names region(s) that exclude the user.
    #     (This is checked against the location string only, not the whole posting text.)
    loc_field = (opp.location_raw or "").lower()
    if loc_field:
        loc_excludes = _has(loc_field, _EXCLUDES_ET) or _has_token(loc_field, _EXCLUDES_ET_TOKENS)
        loc_includes_user = (
            own_country in loc_field
            or (own_city and own_city in loc_field)
            or _has(loc_field, ("africa", "emea"))
            or _has(loc_field, _EAST_AFRICA)
            or _has(loc_field, _INCLUDES_AFRICA)
        )
        if loc_excludes and not loc_includes_user:
            hit = next((p for p in _EXCLUDES_ET if p in loc_field), "region-restricted")
            ev.append(f"location excludes {profile.location.country_name} ('{opp.location_raw}', '{hit}')")
            return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.85, ev)

    # Does the posting name the user's own location as in-scope? (positive, checked before excludes)
    names_user_region = (
        own_country in hay
        or (own_city and own_city in hay)
        or _has(hay, _EAST_AFRICA)
        or _has(hay, ("africa", "emea"))
    )

    # 3) Remote restricted to a region that excludes Ethiopia — but not if the user's region is also named.
    remote_restricted = _has(hay, _EXCLUDES_ET) or _has_token(hay, _EXCLUDES_ET_TOKENS)
    if remote_restricted and not names_user_region and not _has(hay, _INCLUDES_AFRICA):
        hit = next((p for p in _EXCLUDES_ET if p in hay), "region-restricted")
        ev.append(f"remote restricted to a region excluding {profile.location.country_name} ('{hit}')")
        return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.8, ev)

    # 4) Onsite in a foreign country.
    onsite = opp.remote_status == RemoteStatus.ONSITE or _has(hay, ("on-site", "on site", "in-office", "in office"))
    if onsite and opp.location_raw:
        loc = opp.location_raw.lower()
        local = own_country in loc or (own_city and own_city in loc) or own_code in loc.split()
        if local:
            # Onsite in the user's own country: eligible but not a remote match. No category fits
            # cleanly; surface it honestly rather than miscategorize. Flagged for spine review.
            ev.append("onsite in the user's own country — eligible but not remote; category gap flagged")
            return Eligibility(EligibilityCategory.UNKNOWN, 0.4, ev)
        ev.append(f"onsite in a foreign location ('{opp.location_raw}')")
        return Eligibility(EligibilityCategory.ONSITE_FOREIGN, 0.8, ev)

    # 5) Remote region that includes Ethiopia.
    if names_user_region:
        hit = next((p for p in ("africa", "emea", *_EAST_AFRICA) if p in hay), profile.location.country_name)
        ev.append(f"remote scope includes the user's region ('{hit.strip()}')")
        conf = 0.7
        if _has(hay, _US_HOURS):
            ev.append("but requires US-hours overlap — impractical from UTC+3")
            conf -= 0.2
        elif _has(hay, _EU_HOURS):
            ev.append("EU-hours overlap — workable from UTC+3")
            conf += 0.05
        return Eligibility(EligibilityCategory.REMOTE_REGION_INCLUDES_USER, min(conf, 0.9), ev)

    # 6) Worldwide remote.
    if _has(hay, _WORLDWIDE) or _has(hay, _INCLUDES_AFRICA):
        hit = next((p for p in (*_WORLDWIDE, *_INCLUDES_AFRICA) if p in hay), "worldwide")
        ev.append(f"worldwide remote ('{hit}')")
        conf = 0.75
        if _has(hay, _US_HOURS):
            ev.append("but requires US-hours overlap — impractical from UTC+3")
            conf -= 0.2
        return Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, conf, ev)

    # 7) No explicit signal — honestly unknown. Surfaced, never dropped.
    ev.append("no explicit location or authorization signal found — eligibility unknown")
    return Eligibility(EligibilityCategory.UNKNOWN, 0.3, ev)
