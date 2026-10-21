"""Decision facts for one item (spec 2026-10-21 §4.5): what the job is, what it asks for, what it pays,
the hours, and what it says about location — the summary a person decides on without opening the
posting. Deterministic text extraction, no model. Not spine.

Headings arrive flattened by `html_to_text` ("… Requirements 2+ years of …"), so they are matched as
substrings, earliest first. A heading written with a capital letter is matched case-sensitively; an
all-lowercase one ("deine aufgaben") in any case. A field that is not found is omitted, never invented.
"""

from __future__ import annotations

import re

from . import _geo
from .models import Opportunity
from .score import pay_of

ROLE_HEADINGS = ("About the role", "The role entails", "What you'll do", "What You'll Do", "What You Will Do",
                 "Responsibilities", "Key Responsibilities", "Role Overview", "Scope of Work", "Job Summary",
                 "Position Overview", "Your tasks", "deine aufgaben")
ASKS_HEADINGS = ("Requirements", "Qualifications", "What we are looking for", "What We're Looking For",
                 "What we're looking for in you", "About you", "What You'll Need", "What You'll Have",
                 "Required Skills", "Skills, Knowledge and Expertise", "Who We're Looking For", "Who You Are",
                 "dein profil")
_OTHER_HEADINGS = ("Nice to have", "Nice-to-have", "Preferred", "Bonus", "Benefits", "What we offer", "Why join",
                   "Extras", "Perks", "Compensation", "About")
_STOP_HEADINGS = ROLE_HEADINGS + ASKS_HEADINGS + _OTHER_HEADINGS
ROLE_MAX, ASKS_MAX = 250, 350

_HOURS = re.compile(r"\d+\s*(?:[-–]|to)?\s*\d*\s*\+?\s*(hours|hrs)\s*(/|per|a)\s*week", re.IGNORECASE)
# The §4.1 location shapes (a capitalised place: "based in Europe", "Remote (EMEA)") or a
# working-hours/timezone statement; "<place>-based" separately, since most "-based" words in the stored
# bodies are not places ("Performance-based", "Linux-based", "LLM-based").
_LOCATION = re.compile(r"\b(?:based|located|resid(?:e|ing|ent)|living)\s+in\s+(?:the\s+)?[A-Z]|"
                       r"\bRemote\s*\(|\btime ?zones?\b|\boverlap\b|\b(?:GMT|UTC|CET)\b")
_PLACE_BASED = re.compile(r"\b([A-Z][A-Za-z.]*)-based\b")
_PLACES = (_geo.COUNTRIES | _geo.REGIONS_EXCLUDING_AFRICA | _geo.REGIONS_INCLUDING_AFRICA | _geo.US_STATES
           | set(_geo.CITIES))
# A heading's tail ("What we are looking for in you", "What You'll Need to Succeed") is not content.
_HEADING_TAIL = re.compile(r"^(?:in you|to succeed)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_LOCATION_MAX = 200


def _find(text: str, heading: str, start: int = 0) -> int:
    if heading.islower():
        return text.lower().find(heading, start)
    return text.find(heading, start)


def _earliest(text: str, headings: tuple[str, ...], start: int = 0) -> tuple[int, str] | None:
    hits = [(i, h) for h in headings if (i := _find(text, h, start)) >= 0]
    # earliest; at the same position the longer heading ("Key Responsibilities" over "Responsibilities")
    return min(hits, key=lambda x: (x[0], -len(x[1]))) if hits else None


def _cut(text: str, n: int) -> str:
    """At most `n` chars, cut at a word boundary with "…"."""
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def _section(text: str, headings: tuple[str, ...], n: int) -> str | None:
    """Up to `n` chars after the earliest heading, stopping at the next known heading."""
    hit = _earliest(text, headings)
    if hit is None:
        return None
    begin = hit[0] + len(hit[1])
    nxt = _earliest(text, _STOP_HEADINGS, begin)
    body = _HEADING_TAIL.sub("", text[begin: nxt[0] if nxt else len(text)].lstrip())
    body = body.lstrip(" :–—-\n").strip()
    return _cut(body, n) or None


def _is_location(sentence: str) -> bool:
    return bool(_LOCATION.search(sentence)
                or any(m.group(1).lower() in _PLACES for m in _PLACE_BASED.finditer(sentence)))


def key_facts(opp: Opportunity) -> dict[str, str]:
    """{role, asks, pay, hours, location} — only the fields found."""
    text = (opp.description or "").replace("’", "'")   # "What You’ll Do" matches "What You'll Do"
    facts: dict[str, str] = {}
    if role := _section(text, ROLE_HEADINGS, ROLE_MAX):
        facts["role"] = role
    if asks := _section(text, ASKS_HEADINGS, ASKS_MAX):
        facts["asks"] = asks
    verdict, snippet = pay_of(opp)
    if verdict != "unstated":
        facts["pay"] = snippet if verdict == "stated" else f"{verdict}" + (f" — {snippet}" if snippet else "")
    if m := _HOURS.search(text):
        facts["hours"] = m.group(0)
    sentences = [_cut(s.strip(), _LOCATION_MAX) for s in _SENTENCE.findall(text) if _is_location(s)]
    if sentences:
        facts["location"] = " ".join(sentences[:2])
    return facts
