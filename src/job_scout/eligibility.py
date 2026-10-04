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

from . import _geo
from .config import UserProfile
from .models import Eligibility, EligibilityCategory, Opportunity, RemoteStatus

# --------------------------------------------------------------------------------------------- #
# Pattern vocabulary. Short tokens (us, uk, eu) use word boundaries to avoid matching inside other
# words ("queue", "bus"); phrases use plain substring. All matching is lowercase.
# --------------------------------------------------------------------------------------------- #

# Regions/scopes that INCLUDE Ethiopia (Africa). Used only as a guard against the body-text
# exclusion rule (step 4) — never as positive evidence.
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

_WORLDWIDE = (
    "work from anywhere", "fully remote worldwide", "remote worldwide", "remote - global", "remote, global",
    "no location requirement", "location independent", "anywhere in the world", "hire anywhere", "any country",
)

# Labels for one location segment (spec S2).
USER, WORLD, BARE, ELSEWHERE, OTHER = "USER", "WORLD", "BARE", "ELSEWHERE", "OTHER"

_SEGMENT_SPLIT = re.compile(r";|\||/| or | and ")
_EDGE_CHARS = " \t-–—,:()[]."
_TITLE_MARKER = re.compile(r"[-,(]\s*(US|USA|UK|EU|EMEA|APAC|LATAM|AMER|[A-Z][a-z]+)\)?\s*(\[.*\])?$")


def _has(hay: str, needles) -> bool:
    return any(n in hay for n in needles)


def _has_token(hay: str, patterns) -> bool:
    return any(re.search(p, hay) for p in patterns)


def _find_term(text: str, terms) -> str | None:
    """The first term (longest first) present in `text` as a whole word/phrase, or None."""
    for t in sorted(terms, key=len, reverse=True):
        if t and re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", text):
            return t
    return None


MIXED = "MIXED"   # verdict only: places elsewhere plus an unqualified/unrecognized segment

_ELSEWHERE_TERMS = _geo.COUNTRIES | _geo.REGIONS_EXCLUDING_AFRICA | set(_geo.CITIES) | _geo.US_STATES
# Multi-word names that contain " and " must survive segment splitting ("Bosnia and Herzegovina").
_AND_NAMES = sorted((t for t in _ELSEWHERE_TERMS | _geo.REGIONS_INCLUDING_AFRICA if " and " in t), key=len, reverse=True)


def _label_segment(raw: str, profile: UserProfile, remote_mode: bool = True) -> tuple[str, str]:
    """Label one location segment: (label, the token that decided it).

    * USER: the user's country or city; or — for a remote role only — a region that includes them.
      A region does not make an onsite job in a foreign city reachable ("London, UK (EMEA HQ)").
      Region words inside another place's name don't count ("South Africa", "North Africa").
    * ELSEWHERE beats USER when the segment says "<elsewhere> only" ("EMEA (Europe only)"), and
      beats a worldwide word in the same segment ("Anywhere in the US").
    """
    raw = raw.strip().replace(" & ", " and ")
    low = re.sub(r"(?<![a-z])remote(?![a-z])", " ", raw.lower())
    low = re.sub(r"\s+", " ", low).strip(_EDGE_CHARS).strip()
    if not low:
        return BARE, "remote"
    own_country = profile.location.country_name.lower()
    own_city = (profile.location.city or "").lower()
    own_code = profile.location.country_code.upper()

    elsewhere_terms = _ELSEWHERE_TERMS - {own_country, own_city}
    elsewhere = _find_term(low, elsewhere_terms)
    if elsewhere is None:
        tail = raw.rstrip(_EDGE_CHARS)
        if _geo.US_STATE.search(tail) and tail[-2:] != own_code:
            elsewhere = tail[-2:]
    if elsewhere and re.search(r"\b(only|exclusively)\b", low):
        return ELSEWHERE, f"{elsewhere} only"

    # Mask elsewhere names that contain a user term before looking for the user's region.
    masked = low
    for t in sorted(elsewhere_terms, key=len, reverse=True):
        if any(u in t for u in _geo.REGIONS_INCLUDING_AFRICA | {own_country}) and t in masked:
            masked = re.sub(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", " ", masked)
    user_terms = {own_country, own_city} | (set(_geo.REGIONS_INCLUDING_AFRICA) if remote_mode else set())
    hit = _find_term(masked, user_terms - {""})
    if hit:
        return USER, hit
    if elsewhere:
        return ELSEWHERE, elsewhere
    world = _find_term(low, _geo.WORLDWIDE_TOKENS)
    if world:
        return WORLD, world
    return OTHER, low


def _classify_location(loc_raw: str | None, title: str, profile: UserProfile,
                       remote_mode: bool = True) -> tuple[str, str] | None:
    """Read the LOCATION field (plus a trailing region marker in the title) into one verdict.

    Returns (verdict, evidence) with verdict in USER / WORLD / ELSEWHERE — decisive; MIXED — names
    places elsewhere next to an unqualified segment ("Remote; Remote, Canada"), never positive and
    never decided by body text; BARE / OTHER — the location does not decide, read the body. None
    when there is no location at all.
    """
    loc = loc_raw or ""
    for name in _AND_NAMES:   # protect "bosnia and herzegovina" from the " and " split
        loc = re.sub(re.escape(name), name.replace(" and ", " & "), loc, flags=re.IGNORECASE)
    labelled = [_label_segment(s, profile, remote_mode) for s in _SEGMENT_SPLIT.split(loc) if s.strip()]
    m = _TITLE_MARKER.search(title or "")
    if m:
        t_label, _ = _label_segment(m.group(1), profile, remote_mode)
        if t_label == ELSEWHERE:
            # The title says where the role is; a bare "Remote" location is qualified by it.
            labelled = [x for x in labelled if x[0] != BARE] + [(ELSEWHERE, f"title marker '{m.group(1)}'")]
    if not labelled:
        return None
    labels = {lab for lab, _ in labelled}
    for decisive in (USER, WORLD):
        if decisive in labels:
            return decisive, next(h for lab, h in labelled if lab == decisive)
    if ELSEWHERE in labels:
        hits = ", ".join(h for lab, h in labelled if lab == ELSEWHERE)
        return (MIXED if labels & {BARE, OTHER} else ELSEWHERE), hits
    return (BARE if BARE in labels else OTHER), ""


_QUALIFIER_WINDOW = 60


def _unqualified_worldwide_phrase(hay: str, own_country: str) -> str | None:
    """The first `_WORLDWIDE` phrase in `hay` not followed (within a short window) by a named place.

    US-hours phrases are removed from the window first: "worldwide, but overlap with US business
    hours" is a practical penalty, not a location restriction.
    """
    places = (_ELSEWHERE_TERMS - {own_country}) - {"us"} | {"us only", "the us", "in us", "u.s."}
    for p in _WORLDWIDE:
        for m in re.finditer(re.escape(p), hay):
            window = hay[m.end(): m.end() + _QUALIFIER_WINDOW]
            for h in _US_HOURS:
                window = window.replace(h, " ")
            if _find_term(window, places) is None:
                return p
    return None


def _program_verdict(opp: Opportunity, profile: UserProfile) -> Eligibility:
    """A curated known_programs round: eligibility comes from the program's own dated rule."""
    from .sources.known_programs import geo_evidence, geo_verdict

    country = profile.location.country_name
    verdict = geo_verdict(opp.ats_job_id, country)
    ev = geo_evidence(opp.ats_job_id)
    if verdict == "eligible":
        return Eligibility(EligibilityCategory.STIPEND_PROGRAM_GLOBAL, 0.9, ev)
    if verdict == "excluded":
        return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.85,
                           [f"the program excludes {country}", *ev])
    return Eligibility(EligibilityCategory.UNKNOWN, 0.5,
                       [f"geographic eligibility not verified for {country}", *ev])


def classify_eligibility(opp: Opportunity, profile: UserProfile) -> Eligibility:
    """Return an honest eligibility judgement for `opp` given the user's `profile`.

    Order: (1) a curated program round → the program's own rule; (2) a foreign work-authorization
    requirement; then the LOCATION field decides — it names the user's region → included; worldwide
    → worldwide; only places elsewhere → excluded, and no description text can override that. Only
    when the location says nothing decisive ("Remote", unrecognized, absent) is the body read, and
    then only for an explicit worldwide phrase. Generic words in the body ("global", "EMEA") are
    never positive evidence — they are employer boilerplate (spec S2, C4).
    """
    hay = f" {opp.title} {opp.description} {opp.location_raw or ''} ".lower()
    ev: list[str] = []

    own_country = profile.location.country_name.lower()
    own_code = profile.location.country_code.lower()
    own_city = (profile.location.city or "").lower()
    authed = {c.lower() for c in profile.work_authorization}

    # 1) A curated program round — its eligibility is the program's own dated rule, never assumed.
    if opp.ats_provider == "known_programs":
        return _program_verdict(opp, profile)

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

    # 3) The LOCATION field decides first; description text cannot override it. A region that includes
    #    the user only counts for a remote role (an onsite job in London is not reachable via "EMEA").
    loc_low = (opp.location_raw or "").lower()
    remote_mode = opp.remote_status == RemoteStatus.REMOTE or "remote" in loc_low
    onsite = opp.remote_status in (RemoteStatus.ONSITE, RemoteStatus.HYBRID) or (
        opp.remote_status == RemoteStatus.UNKNOWN and _has(hay, ("on-site", "on site", "onsite", "in-office", "in office"))
    )
    loc = _classify_location(opp.location_raw, opp.title, profile, remote_mode=remote_mode)
    where = f"location '{opp.location_raw}'" if opp.location_raw else "location"
    if loc is not None:
        verdict, hit = loc
        if verdict == USER:
            if onsite and hit in (own_country, own_city):
                # Onsite in the user's own country: eligible but not remote. No category fits; keep the
                # Gate-0 decision (STATE Decisions #1) — honest UNKNOWN, never dropped.
                ev.append(f"{where}: onsite in the user's own country — eligible but not remote; category gap flagged")
                return Eligibility(EligibilityCategory.UNKNOWN, 0.4, ev)
            ev.append(f"{where} includes {profile.location.country_name} ('{hit}')")
            return Eligibility(EligibilityCategory.REMOTE_REGION_INCLUDES_USER, 0.8, ev)
        if verdict == WORLD:
            ev.append(f"{where} is worldwide ('{hit}')")
            return Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, 0.85, ev)
        if verdict == ELSEWHERE:
            ev.append(f"{where} names only places outside {profile.location.country_name} ({hit})")
            if remote_mode:
                return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.85, ev)
            return Eligibility(EligibilityCategory.ONSITE_FOREIGN, 0.8, ev)
        if verdict == MIXED:
            # Places elsewhere next to an unqualified segment: not positive, not confidently negative,
            # and not something body boilerplate may decide either way.
            ev.append(f"{where} names places outside {profile.location.country_name} ({hit}) "
                      "next to an unqualified segment — eligibility unknown")
            return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)

    # 4) The location is bare ("Remote"), unrecognized, or absent → read the body, conservatively.
    #    Kept from before: a body that names an excluding region, with no sign of the user's region.
    names_user_region = (
        own_country in hay
        or (own_city and own_city in hay)
        or _has(hay, _EAST_AFRICA)
        or _has(hay, ("africa", "emea"))
    )
    remote_restricted = _has(hay, _EXCLUDES_ET) or _has_token(hay, _EXCLUDES_ET_TOKENS)
    if remote_restricted and not names_user_region and not _has(hay, _INCLUDES_AFRICA):
        hit = next((p for p in _EXCLUDES_ET if p in hay), "region-restricted")
        ev.append(f"remote restricted to a region excluding {profile.location.country_name} ('{hit}')")
        return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.8, ev)

    #    An explicit worldwide phrase in the body (never a bare "global"/"EMEA" word), and only when
    #    the words right after it do not name a place ("work from anywhere within the US").
    phrase = _unqualified_worldwide_phrase(hay, own_country)
    if phrase:
        ev.append(f"{where} not decisive; body states worldwide ('{phrase}')")
        conf = 0.7
        if _has(hay, _US_HOURS):
            ev.append("but requires US-hours overlap — impractical from UTC+3")
            conf -= 0.2
        return Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, round(conf, 2), ev)

    # 5) No decisive signal — honestly unknown. Surfaced, never dropped.
    if loc is not None and loc[0] == BARE:
        ev.append(f"{where} is plain 'Remote' with no stated scope — eligibility unknown")
        return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)
    ev.append("no explicit location or authorization signal found — eligibility unknown")
    return Eligibility(EligibilityCategory.UNKNOWN, 0.3, ev)
