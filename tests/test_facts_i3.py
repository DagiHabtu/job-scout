"""Iteration 3 §4.5 — decision facts on every item. Bodies named by label_id are the stored texts
(tests/fixtures/labels_2026-10-21_records.json)."""

from __future__ import annotations

import json
from pathlib import Path

from job_scout.facts import ASKS_MAX, ROLE_MAX, key_facts
from job_scout.models import Opportunity

ROOT = Path(__file__).resolve().parents[1]
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))
REC = {r["label_id"]: r["record"] for r in _FX["records"]}   # one record per label (CloudCops' twin collapses)


def _opp(body, title="Engineer"):
    return Opportunity(title=title, company="X", apply_url="https://x", canonical_url="https://x",
                       description=body)


def _facts(label):
    r = REC[label]
    return key_facts(_opp(r.get("description") or "", r["title"]))


def test_role_and_asks_from_flattened_headings_stop_at_next_heading():
    f = key_facts(_opp("Acme builds tools. Responsibilities Build APIs. Fix bugs. Requirements Python. SQL. "
                       "Nice to have Go. Benefits Laptop."))
    assert f["role"] == "Build APIs. Fix bugs."
    assert f["asks"] == "Python. SQL."


def test_earliest_heading_wins_and_longer_heading_at_same_place():
    f = key_facts(_opp("Key Responsibilities Ship code. What you'll do Other. Qualifications C."))
    assert f["role"] == "Ship code."


def test_lowercase_heading_matches_any_case_and_curly_apostrophe():
    assert key_facts(_opp("Deine Aufgaben Code schreiben. Dein Profil Git."))["role"] == "Code schreiben."
    assert key_facts(_opp("What You’ll Do Build. Who You Are Kind."))["role"] == "Build."


def test_heading_tail_is_not_content():
    assert key_facts(_opp("What we are looking for in you Rust skills."))["asks"] == "Rust skills."
    assert key_facts(_opp("What You'll Need to Succeed A degree."))["asks"] == "A degree."


def test_long_sections_cut_at_word_boundary():
    f = key_facts(_opp("Responsibilities " + "word " * 100 + "Requirements " + "skill " * 100))
    assert f["role"].endswith("…") and len(f["role"]) <= ROLE_MAX + 1 and " wor…" not in f["role"]
    assert f["asks"].endswith("…") and len(f["asks"]) <= ASKS_MAX + 1


def test_hours():
    assert key_facts(_opp("You will work 20-30 hours per week."))["hours"] == "20-30 hours per week"
    assert key_facts(_opp("Expect 40 hrs/week."))["hours"] == "40 hrs/week"


def test_location_shapes_and_timezones_up_to_two_sentences():
    f = key_facts(_opp("We build tools. You must be based in Europe. Overlap with CET is needed. Pay is good. "
                       "Remote (EMEA) only."))
    assert f["location"] == "You must be based in Europe. Overlap with CET is needed."
    assert key_facts(_opp("We hire US-based engineers."))["location"] == "We hire US-based engineers."


def test_non_place_based_words_are_not_location():
    """Stored bodies: "Performance-based bonus", "Linux-based", Avary's "LLM-based recruiting systems"."""
    assert "location" not in key_facts(_opp("Performance-based bonus. Linux-based tools. LLM-based systems."))
    assert "location" not in _facts("avary")


def test_missing_fields_are_omitted():
    assert key_facts(_opp("")) == {}
    assert key_facts(_opp("We are a team that builds things.")) == {}


def test_pay_from_4_4():
    assert _facts("vantum")["pay"] == "$500 to $1,000 USD per month"
    assert _facts("holiday")["pay"].startswith("unpaid")


def test_stored_picked_items():
    assert _facts("canon-kernel")["asks"].startswith("Well-organized and motivated self-starter")
    assert "every timezone" in _facts("canon-kernel")["location"]
    assert _facts("emetlab")["asks"].startswith("A degree in Computer Science")
    assert "GMT+7" in _facts("vantum")["location"]


def test_coverage_on_appendix_a_bodies():
    """§4.5 acceptance: asks ≥ 80%, role ≥ 70% of the stored Appendix A descriptions."""
    facts = [_facts(label) for label in REC]
    assert sum("asks" in f for f in facts) / len(facts) >= 0.80
    assert sum("role" in f for f in facts) / len(facts) >= 0.70
