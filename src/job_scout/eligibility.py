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
_EXCLUDES_ET_TOKENS = (r"\buk\b", r"\beu\b")  # bare tokens, boundary-guarded ("US" is case-sensitive, step 4)

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
_SPONSORSHIP = frozenset({"no visa sponsorship", "not sponsor", "will not sponsor", "unable to sponsor",
                          "without sponsorship"})
_RESIDENCY_AUTH = frozenset({"must reside in the", "must be located in the", "must be based in"})
# GSoC-style benign phrasing that is NOT a foreign-auth requirement.
_BENIGN_AUTH = ("your country of residence", "in your country", "country you reside")

# US-hours requirements — a practical (not legal) obstacle from UTC+3; EU-hours is fine for ET.
_US_HOURS = ("pacific time", "pst", "pdt", "eastern time", " est ", " edt ", "us business hours", "overlap with us")
_EU_HOURS = ("central european", " cet ", " cest ", "european hours", "overlap with european", "gmt+1", "gmt+2")

_WORLDWIDE = (
    "work from anywhere", "fully remote worldwide", "remote worldwide", "remote - global", "remote, global",
    "no location requirement", "location independent", "anywhere in the world", "hire anywhere", "any country",
    "no geographic restrictions", "no geographical restrictions", "remote (global)",
)

# Labels for one location segment (spec S2).
USER, WORLD, BARE, ELSEWHERE, OTHER = "USER", "WORLD", "BARE", "ELSEWHERE", "OTHER"
# The aggregator's "no restriction listed" marker (spec 2026-10-21 §4.1): like BARE, the body decides.
UNSTATED = "UNSTATED"
UNSTATED_EVIDENCE = "Himalayas lists no location restriction; the posting states none"

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

_EXCLUSION = re.compile(r"\b(?:except(?: for)?|excluding|excl\.?|not including)(?![a-z])")

_ELSEWHERE_TERMS = (_geo.COUNTRIES | _geo.REGIONS_EXCLUDING_AFRICA | set(_geo.CITIES) | _geo.US_STATES
                    | _geo.SUBNATIONAL)
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
    low = re.sub(r"(?<![a-z])(?:fully |100% )?remote(?![a-z])", " ", raw.lower())
    low = re.sub(r"\s+", " ", low).strip(_EDGE_CHARS).strip()
    if not low:
        return BARE, "remote"
    own_country = profile.location.country_name.lower()
    own_city = (profile.location.city or "").lower()
    own_code = profile.location.country_code.upper()

    # "Global (excluding US)", "EMEA, excluding Ethiopia": the excluded part is not where the role
    # is. If it names the user → excluded; otherwise label only the part before it.
    m = _EXCLUSION.search(low)
    if m:
        excluded = low[m.end():]
        if _find_term(excluded, {own_country, own_city} - {""}):
            return ELSEWHERE, f"excludes {profile.location.country_name}"
        low = low[: m.start()].strip(_EDGE_CHARS).strip()
        raw = raw[: _EXCLUSION.search(raw.lower()).start()]
        if not low:
            return BARE, "remote"

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
    never decided by body text; BARE / UNSTATED / OTHER — the location does not decide, read the body.
    None when there is no location at all.
    """
    unstated = (loc_raw or "").strip() == _geo.NO_RESTRICTION_LISTED
    loc = "" if unstated else (loc_raw or "")
    for name in _AND_NAMES:   # protect "bosnia and herzegovina" from the " and " split
        loc = re.sub(re.escape(name), name.replace(" and ", " & "), loc, flags=re.IGNORECASE)
    labelled = [_label_segment(s, profile, remote_mode) for s in _SEGMENT_SPLIT.split(loc) if s.strip()]
    m = _TITLE_MARKER.search(title or "")
    title_elsewhere = False
    if m:
        t_label, _ = _label_segment(m.group(1), profile, remote_mode)
        if t_label == ELSEWHERE:
            # The title says where the role is; a bare "Remote" location is qualified by it.
            title_elsewhere = True
            labelled = [x for x in labelled if x[0] != BARE] + [(ELSEWHERE, f"title marker '{m.group(1)}'")]
    if not labelled:
        return (UNSTATED, "") if unstated else None
    labels = {lab for lab, _ in labelled}
    if USER in labels:
        return USER, next(h for lab, h in labelled if lab == USER)
    if WORLD in labels:
        if title_elsewhere:
            # "Worldwide" location vs "… (US)" title: conflicting, so neither side decides (final
            # review L9 — Himalayas writes "Worldwide" for empty restrictions).
            hits = ", ".join(h for lab, h in labelled)
            return MIXED, hits
        return WORLD, next(h for lab, h in labelled if lab == WORLD)
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
    places = _elsewhere_places(own_country)
    for p in _WORLDWIDE:
        for m in re.finditer(re.escape(p), hay):
            window = hay[m.end(): m.end() + _QUALIFIER_WINDOW]
            for h in _US_HOURS:
                window = window.replace(h, " ")
            if _find_term(window, places) is None:
                return p
    return None


_RESIDENCE = re.compile(r"\b(?:located|reside|residing|resident|based|live|living)\s+in\s+")


def _elsewhere_places(own_country: str) -> set[str]:
    return (_ELSEWHERE_TERMS - {own_country}) - {"us"} | {"us only", "the us", "in us", "u.s."}


def _residency_elsewhere(hay: str, own_country: str) -> str | None:
    """A place outside the user's country named right after "located/reside/based/live in", or None."""
    places = _elsewhere_places(own_country)
    for m in _RESIDENCE.finditer(hay):
        window = re.sub(r"^(?:the|one of the)\s+", "", hay[m.end(): m.end() + 40])
        term = _find_term(window, places)
        if term and window.startswith(term):
            return term
    return None


def _followed_by(hay: str, phrase: str, terms: set[str]) -> bool:
    """Every occurrence of `phrase` is followed (within 40 chars, same sentence) by one of `terms`."""
    ends = [m.end() for m in re.finditer(re.escape(phrase), hay)]
    return bool(ends) and all(_find_term(re.split(r"[.;:\n]", hay[e: e + 40])[0], terms) for e in ends)


# A body sentence that limits who may apply to named places: "must be based/located/reside in …",
# "candidates/applicants in …", "open to residents of …". The captured clause runs to the sentence end.
_BODY_RESTRICTION = re.compile(
    r"\b(?:must\s+(?:be\s+)?(?:based|located|resid(?:e|ing)|liv(?:e|ing))\s+in"
    r"|(?:position|role|job)\s+(?:is\s+)?(?:\S+\s+){0,3}?(?:will\s+be\s+|is\s+)?(?:based|located)\s+in"
    r"|(?:candidates|applicants|residents)\s+(?:(?:based|located|residing|living)\s+)?(?:in|of))"
    r"\s+([^.;:\n]{1,80})"
)
_CLAUSE_SPLIT = re.compile(r",|\band\b|\bor\b|/")


def _body_restrictions(description: str, profile: UserProfile):
    """Each body restriction whose places are ALL outside the user's scope, as (match, clause).

    Every part of the clause must name a place elsewhere ("the US and Canada only", "Europe or North
    America"); a part naming the user, the world, or no recognised place ("any time zone") means the
    sentence is not a restriction that excludes the user.
    """
    for m in _BODY_RESTRICTION.finditer((description or "").lower()):
        clause = m.group(1)
        parts = [re.sub(r"^\s*(?:the|either)\s+", "", p).strip() for p in _CLAUSE_SPLIT.split(clause)]
        parts = [p for p in parts if p]
        if parts and all(_label_segment(p, profile)[0] == ELSEWHERE for p in parts):
            yield m, clause.strip()


def _body_restriction_elsewhere(description: str, profile: UserProfile) -> str | None:
    """The clause of the first body restriction naming only places elsewhere, or None."""
    return next((clause for _, clause in _body_restrictions(description, profile)), None)


# Body location statements for a location field that does not decide (spec 2026-10-21 §4.1 step 4).
EXCLUDE, INCLUDE = "EXCLUDE", "INCLUDE"
_PLACE_IN = re.compile(r"\b(?:based|located|resid(?:e|ing|ent)|living)\s+in\s+([^.;:!?\n]{1,80})")
_PLACE_BASED = re.compile(r"[- ]based\b(?!\s+(?:on|upon|off)\b)")
_REMOTE_LIST = re.compile(r"\bremote\s*\(([^()]{1,120})\)")
_PREFERENCE = re.compile(r"\b(?:preferred|nice to have|bonus|a plus|a preference)\b")   # + i3-b
# A pay note is not a location requirement ("The base salary range … is for residents of the United
# States only") — deviation i3-c.
_PAY_NOTE = re.compile(r"\b(?:salary|pay range|base pay|compensation)\b")
_PREFERENCE_WINDOW = 250
_PREFERENCE_AFTER = re.compile(r"\b(?:is|are|would be|will be)\s+(?:a\s+|an\s+)?(?:strong\s+)?"
                               r"(?:plus|bonus|preferred|nice to have|advantage)\b")
_RELOCATION = re.compile(r"relocat")
_SENTENCE_END = re.compile(r"[.!?:\n]")
# "a US-based company", "our team is based in Berlin": the place describes the employer, not the hire.
# Spec §4.1 guards "-based" with a|an|our|the within three words; "based in" also takes the company
# nouns (deviation i3-a: "We are an innovative SaaS startup based in Portugal").
_ARTICLES = frozenset({"a", "an", "our", "the"})
_EMPLOYER_WORDS = _ARTICLES | {"we", "company", "startup", "firm", "agency", "business", "team",
                               "headquartered", "office", "offices", "customers", "clients", "users", "partners"}
_LEADING_ARTICLE = re.compile(r"^(?:a|an|either|one of the)\s+")
# Also the employer, not the hire (deviation i3-c, stored Himalayas bodies): "US-based employers",
# "U.S.-based companies"; "Based in Melbourne, Australia, we are growing"; and "NOT based in …".
_EMPLOYER_AFTER = re.compile(r"\s+(?:employers?|compan(?:y|ies)|clients?|customers?|business(?:es)?|firms?|"
                             r"startups?|organi[sz]ations?|teams?|brands?|agenc(?:y|ies))\b")
_EMPLOYER_CLAUSE = re.compile(r",\s*(?:we|our)\b")
_NEGATION = frozenset({"not", "aren't", "isn't", "never"})


def _sentence_at(text: str, start: int, end: int) -> str:
    """The sentence around text[start:end]; a ':' ends one too ("… North America) Location: Remote …")."""
    s = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    m = _SENTENCE_END.search(text, end)
    sentence = text[s: m.start() if m else len(text)].strip()
    if len(sentence) > 200:   # a flattened list block: quote the part around the match
        sentence = text[max(s, start - 80): min(m.start() if m else len(text), end + 80)].strip()
    return sentence


def _words_before(text: str, pos: int, n: int = 3) -> set[str]:
    """The last `n` words before `pos`, within its sentence ("A plus: based in …" has none)."""
    head = text[max(0, pos - 60): pos]
    head = _SENTENCE_END.split(head)[-1]
    return set(re.findall(r"[a-z0-9'’]+", head)[-n:])


def _body_location(description: str, profile: UserProfile) -> list[tuple[str, str, int, bool]]:
    """Every body statement of where the hire must be, in text order, as (kind, sentence, position,
    preferred): kind EXCLUDE (names only places elsewhere), INCLUDE (`Remote (<list>)` naming the
    user's region) or WORLD (`Remote (Global)`); `preferred` when a preference word ("preferred",
    "nice to have", "bonus", "a plus") comes within 250 chars before it.

    Shapes: "(based|located|resid…|living) in <place>"; "<place>-based" not describing the employer;
    "Remote (<list>)"; and the older restriction sentences ("must be based in …", "the position will be
    based in …", "candidates in …").
    """
    raw = description or ""
    low = raw.lower()
    own_country = profile.location.country_name.lower()
    places = _elsewhere_places(own_country)
    hits: list[tuple[str, int, int]] = []          # (kind, start, end)

    for m in _PLACE_IN.finditer(low):
        if _words_before(low, m.start()) & (_EMPLOYER_WORDS | _NEGATION) or _EMPLOYER_CLAUSE.search(m.group(1)):
            continue
        parts = [p.strip() for p in _CLAUSE_SPLIT.split(m.group(1)) if p.strip()]
        first = _LEADING_ARTICLE.sub("", parts[0]) if parts else ""
        if first.startswith("the ") and not first.startswith("the us"):
            first = first[4:]
        term = _find_term(first, places)
        if not (term and first.startswith(term)):
            continue
        if any(_label_segment(_LEADING_ARTICLE.sub("", p), profile)[0] in (USER, WORLD) for p in parts[1:]):
            continue
        hits.append((EXCLUDE, m.start(), m.end()))

    based_terms = sorted((places - {"the us", "in us", "us only"}) | {"us"}, key=len, reverse=True)
    for m in _PLACE_BASED.finditer(low):
        before = low[: m.start()]
        term = next((t for t in based_terms if before.endswith(t)
                     and (len(before) == len(t) or not before[-len(t) - 1].isalnum())), None)
        if term is None or (term == "us" and raw[m.start() - 2: m.start()] != "US"):   # "join us based …"
            continue
        start = m.start() - len(term)
        if _words_before(low, start) & (_ARTICLES | _NEGATION) or _EMPLOYER_AFTER.match(low, m.end()):
            continue
        hits.append((EXCLUDE, start, m.end()))

    for m in _REMOTE_LIST.finditer(low):
        inner = m.group(1)
        if _RELOCATION.search(inner):                   # "Remote (Relocation to Portugal Available)"
            continue
        verdict = _classify_location(inner, "", profile)
        kind = {ELSEWHERE: EXCLUDE, USER: INCLUDE, WORLD: WORLD}.get(verdict[0] if verdict else None)
        if kind:
            hits.append((kind, m.start(), m.end()))

    for m, _ in _body_restrictions(raw, profile):
        hits.append((EXCLUDE, m.start(), m.end()))

    out = []
    for kind, start, end in sorted(hits, key=lambda h: h[1]):
        sentence = _sentence_at(raw, start, end)
        if kind == EXCLUDE and _PAY_NOTE.search(sentence.lower()):
            continue
        # also a predicate preference after it in the same sentence ("Being based in Europe is a plus") —
        # deviation i3-b; the spec reads only the 250 chars before. Predicate form only: a flattened
        # heading after a requirement ("… US-based Nice to Have Living in …") is not one.
        preferred = bool(_PREFERENCE.search(low[max(0, start - _PREFERENCE_WINDOW): start])
                         or _PREFERENCE_AFTER.search(sentence.lower()))
        out.append((kind, sentence, start, preferred))
    return out


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

    # The location verdict is computed first so step 2 can tell a decisive worldwide/user-region
    # location apart (final review M1); the decision ORDER below is unchanged.
    loc_low = (opp.location_raw or "").lower()
    remote_mode = opp.remote_status == RemoteStatus.REMOTE or "remote" in loc_low
    loc = _classify_location(opp.location_raw, opp.title, profile, remote_mode=remote_mode)

    # 2) Foreign work authorization required (unless the benign 'your country of residence' phrasing).
    #    Not counted: a residency phrase that names the user's region or "anywhere" ("must be based in
    #    EMEA"), and — when the location is decisively worldwide / includes the user — a visa-
    #    sponsorship line (a remote hire needs no visa).
    user_terms = {own_country, own_city, *_geo.REGIONS_INCLUDING_AFRICA, *_geo.WORLDWIDE_TOKENS} - {""}
    auth_hits = [p for p in _WORK_AUTH if p in hay]
    auth_hits = [p for p in auth_hits if not (p in _RESIDENCY_AUTH and _followed_by(hay, p, user_terms))]
    if loc is not None and loc[0] in (USER, WORLD):
        auth_hits = [p for p in auth_hits if p not in _SPONSORSHIP]
    if auth_hits and not _has(hay, _BENIGN_AUTH):
        # If it explicitly requires auth in a country the user already has, it is not disqualifying.
        # The country code is matched on a word boundary — a bare substring test lets a 2-letter code
        # like "et" match inside ordinary words ("meetings", "get") and silently mask a real
        # foreign-auth requirement. The country NAME stays a plain substring (it is distinctive).
        owns_named = own_country in hay or re.search(rf"\b{re.escape(own_code)}\b", hay) is not None
        requires_owned = own_code in authed and owns_named
        if not requires_owned:
            ev.append(f"requires work authorization the user lacks ('{auth_hits[0]}')")
            return Eligibility(EligibilityCategory.REQUIRES_WORK_AUTH, 0.85, ev)

    # 3) The LOCATION field decides first; description text cannot override it. A region that includes
    #    the user only counts for a remote role (an onsite job in London is not reachable via "EMEA").
    onsite = opp.remote_status in (RemoteStatus.ONSITE, RemoteStatus.HYBRID) or (
        opp.remote_status == RemoteStatus.UNKNOWN and _has(hay, ("on-site", "on site", "onsite", "in-office", "in office"))
    )
    where = f"location '{opp.location_raw}'" if opp.location_raw else "location"
    if loc is not None:
        verdict, hit = loc
        if verdict == USER:
            if onsite and hit in (own_country, own_city):
                # Onsite in the user's own country: eligible but not remote. No category fits; keep the
                # Gate-0 decision (STATE Decisions #1) — honest UNKNOWN, never dropped.
                ev.append(f"{where}: onsite in the user's own country — eligible but not remote; category gap flagged")
                return Eligibility(EligibilityCategory.UNKNOWN, 0.4, ev)
        if verdict in (USER, WORLD):
            # A worldwide / user-region location (Himalayas synthesizes "Worldwide" from an empty
            # field) does not override a body sentence restricting applicants to places elsewhere.
            restricted = _body_restriction_elsewhere(opp.description, profile)
            if restricted:
                ev.append(f"{where} {'is worldwide' if verdict == WORLD else 'includes the user'}, but the "
                          f"description restricts applicants to '{restricted}' — eligibility unknown")
                return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)
        if verdict == USER:
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

    # 4) The location is bare ("Remote"), the aggregator's "no restriction listed" marker, unrecognized,
    #    or absent → read the body, conservatively (spec 2026-10-21 §4.1). First match wins:
    #    (a) a required location naming only other places → excluded at the disqualify threshold (0.75),
    #        or UNKNOWN 0.5 when the same sentence mentions relocation;
    #    (b) a location preference naming only other places → UNKNOWN 0.45;
    #    both before any worldwide phrase: an explicit region list beats benefit boilerplate ("Remote work
    #    flexibility from anywhere in the world"), as the location field does (Decision #6).
    stated = _body_location(opp.description, profile)
    required = [h for h in stated if h[0] == EXCLUDE and not h[3]]
    preferred = [h for h in stated if h[0] == EXCLUDE and h[3]]
    if required:
        sentence = required[0][1]
        if _RELOCATION.search(sentence.lower()):
            ev.append(f"{where} not decisive; the posting names places outside {profile.location.country_name} "
                      f"but mentions relocation: '{sentence}' — eligibility unknown")
            return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)
        ev.append(f"{where} not decisive; the posting requires a location outside "
                  f"{profile.location.country_name}: '{sentence}'")
        return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.75, ev)
    if preferred:
        ev.append(f"states a location preference: '{preferred[0][1]}'")
        return Eligibility(EligibilityCategory.UNKNOWN, 0.45, ev)

    #    Kept from before: a body that names an excluding region, with no sign of the user's region —
    #    but not for the aggregator marker (deviation i3-d): this coarse substring rule ("apac" inside
    #    "capacity", "roles outside the U.S.") would turn listings that used to read worldwide into
    #    confident exclusions; for the marker only the shapes above may exclude.
    unstated = loc is not None and loc[0] == UNSTATED
    names_user_region = unstated or (
        own_country in hay
        or (own_city and own_city in hay)
        or _has(hay, _EAST_AFRICA)
        or _has(hay, ("africa", "emea"))
    )
    #    "US" is matched in its original case — the pronoun "us" ("join us") is not a country (final
    #    review H1).
    raw_hay = f" {opp.title} {opp.description} {opp.location_raw or ''} "
    remote_restricted = (_has(hay, _EXCLUDES_ET) or _has_token(hay, _EXCLUDES_ET_TOKENS)
                         or re.search(r"\bUS\b", raw_hay) is not None)
    if remote_restricted and not names_user_region and not _has(hay, _INCLUDES_AFRICA):
        hit = next((p for p in _EXCLUDES_ET if p in hay), "region-restricted")
        ev.append(f"remote restricted to a region excluding {profile.location.country_name} ('{hit}')")
        return Eligibility(EligibilityCategory.REMOTE_EXCLUDES_USER, 0.8, ev)

    #    (c) "Remote (<list>)" in the body naming the user's region, or "Remote (Global)" — an explicit
    #    statement, not a bare boilerplate word; body evidence, so 0.7 like a worldwide phrase.
    listed = next((h for h in stated if h[0] in (INCLUDE, WORLD)), None)
    if listed:
        if listed[0] == INCLUDE:
            ev.append(f"{where} not decisive; the posting says '{listed[1]}', which includes "
                      f"{profile.location.country_name}")
            return Eligibility(EligibilityCategory.REMOTE_REGION_INCLUDES_USER, 0.7, ev)
        ev.append(f"{where} not decisive; body states worldwide ('{listed[1]}')")
        return Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, 0.7, ev)

    #    An explicit worldwide phrase in the body (never a bare "global"/"EMEA" word), and only when
    #    the words right after it do not name a place ("work from anywhere within the US") and the
    #    body does not require residence elsewhere ("…anywhere in the world, we do require successful
    #    candidates to be located in the United States" — final review H2).
    phrase = _unqualified_worldwide_phrase(hay, own_country)
    residency = _residency_elsewhere(hay, own_country) if phrase else None
    if residency:
        ev.append(f"{where} not decisive; body says '{phrase}' but requires residence in {residency} "
                  "— eligibility unknown")
        return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)
    if phrase:
        ev.append(f"{where} not decisive; body states worldwide ('{phrase}')")
        conf = 0.7
        if _has(hay, _US_HOURS):
            ev.append("but requires US-hours overlap — impractical from UTC+3")
            conf -= 0.2
        return Eligibility(EligibilityCategory.WORLDWIDE_REMOTE, round(conf, 2), ev)

    # 5) No decisive signal — honestly unknown. Surfaced, never dropped. (d) of spec 2026-10-21 §4.1: 0.6
    #    for the aggregator marker, 0.5 for a bare "Remote", 0.3 for no location.
    if loc is not None and loc[0] == UNSTATED:
        ev.append(UNSTATED_EVIDENCE)
        return Eligibility(EligibilityCategory.UNKNOWN, 0.6, ev)
    if loc is not None and loc[0] == BARE:
        ev.append(f"{where} is plain 'Remote' with no stated scope — eligibility unknown")
        return Eligibility(EligibilityCategory.UNKNOWN, 0.5, ev)
    ev.append("no explicit location or authorization signal found — eligibility unknown")
    return Eligibility(EligibilityCategory.UNKNOWN, 0.3, ev)
