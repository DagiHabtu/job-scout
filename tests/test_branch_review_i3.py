"""Iteration 3 whole-branch review findings — each written as a test before its fix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from job_scout.facts import key_facts
from job_scout.labels import LabelParseError, label_lines, parse_label_comment
from job_scout.models import EmploymentType as ET, Opportunity
from job_scout.score import pay_of, role_family_ok

ROOT = Path(__file__).resolve().parents[1]
_FX = json.loads((ROOT / "tests" / "fixtures" / "labels_2026-10-21_records.json").read_text(encoding="utf-8"))
REC = {r["label_id"]: r["record"] for r in _FX["records"]}


def _opp(body, title="SWE Intern"):
    return Opportunity(title=title, company="X", apply_url="https://x", canonical_url="https://x",
                       employment_type=ET.INTERNSHIP, description=body)


# M1 — a body that negates "unpaid" is not unpaid.
@pytest.mark.parametrize("body,snippet", [
    ("This is a paid internship, not an unpaid internship. $2,000/month.", "$2,000/month"),
    ("Unlike an unpaid internship, you will earn $25/hour.", "$25/hour"),
])
def test_negated_unpaid_is_not_unpaid(body, snippet):
    assert pay_of(_opp(body)) == ("stated", snippet)


def test_plain_unpaid_still_unpaid():
    assert pay_of(_opp("Note: this is an unpaid internship."))[0] == "unpaid"


# M2 — a performance-based bonus or "paid time off" does not make a salaried post contingent.
@pytest.mark.parametrize("body,snippet", [
    ("Competitive compensation plus performance-based bonuses. $4,000 per month base.", "$4,000 per month"),
    ("Salary: $60,000 per year. Performance-based bonus paid quarterly.", "$60,000 per year"),
    ("$1,000 a month and paid time off; we run a goal-based OKR process.", "$1,000 a month"),
])
def test_bonus_or_paid_time_off_is_not_contingent(body, snippet):
    assert pay_of(_opp(body)) == ("stated", snippet)


def test_makerble_tester_still_contingent():
    r = REC["makerble-test"]
    assert pay_of(_opp(r["description"], r["title"]))[0] == "contingent"


# L4 — "an hour" is a period.
def test_an_hour_is_stated():
    assert pay_of(_opp("Pay $20 an hour, part-time.")) == ("stated", "$20 an hour")


# M3 — the location fact shows the location statement even deep inside a long flattened sentence.
def test_location_fact_keeps_the_match_in_a_long_sentence():
    r = REC["ewor-dev"]
    loc = key_facts(_opp(r["description"], r["title"]))["location"]
    assert "based in Europe" in loc and len(loc) <= 2 * 200 + 1


# L1 — the company on a label line stops before the "eligibility not confirmed" note.
_BODY = ("## Eligible, outside your stated interests\n\n"
         "1. [QA Intern](https://x/1) — Acme — eligibility not confirmed — check it before applying\n"
         "2. [Tester](https://x/2) — eligibility not confirmed — check it before applying\n"
         '<!-- scout-items {"1": "k1", "2": "k2"} -->\n')


def test_label_line_company_excludes_the_note():
    lines = label_lines(_BODY, "apply all")
    assert [ln["company"] for ln in lines] == ["Acme", None]


# L2 — a verb with no items after it is an error, not silently dropped.
def test_verb_without_items_is_an_error():
    with pytest.raises(LabelParseError) as e:
        parse_label_comment("apply 1 maybe", {"1": "a", "2": "b"})
    assert "`maybe (no items after it)`" in str(e.value)


# L3 — "Cybersecurity" is the security family.
def test_cybersecurity_title_is_in_family():
    assert role_family_ok("Cybersecurity Analyst Intern")


# ---- second reviewer ---------------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

from job_scout.labels import item_map_of, latest  # noqa: E402
from job_scout.pipeline import _check_invariant, run_once  # noqa: E402
from job_scout.store import connect  # noqa: E402
from fixtures.gate0 import FakeSource  # noqa: E402
from test_delivery_i3 import MONDAY, TUESDAY, _after_monday_digest, _cfg, _intern, _map, _notify  # noqa: E402


# H1 — a deferred item is delivered on Monday even when Monday's fetch no longer returns it.
def test_deferred_item_not_refetched_is_delivered_on_monday(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    run_once(cfg, [FakeSource("fake", [_intern("Backend Intern B")])], today=TUESDAY)
    s = run_once(cfg, [FakeSource("empty", [])], today=MONDAY)
    md = _notify(tmp_path)
    assert s.notified == 1 and "Backend Intern B" in md and len(_map(md)) == 1
    assert _check_invariant(s)
    conn = connect(cfg.db_path)
    assert conn.execute("SELECT notified_at FROM opportunities WHERE title='Backend Intern B'").fetchone()[0]


def test_deferred_item_outside_14_days_is_not_carried(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    run_once(cfg, [FakeSource("fake", [_intern("Backend Intern B")])], today=TUESDAY)
    s = run_once(cfg, [FakeSource("empty", [])], today=MONDAY + timedelta(days=21))
    assert s.notified == 0


# H1/L1 — a weekday deferral is not a "rejected" sample in the funnel.
def test_deferred_is_not_a_rejected_sample(tmp_path):
    cfg = _cfg(tmp_path)
    _after_monday_digest(cfg)
    s = run_once(cfg, [FakeSource("fake", [_intern("Backend Intern B")])], today=TUESDAY)
    assert s.gate.get("deferred:weekly") == 1
    assert not any("deferred" in str(x) for x in s.internship_funnel.get("rejected_samples", []))


# M1 — `rest` in a later comment covers only items no comment on this issue has named.
def test_rest_in_a_later_comment_keeps_earlier_decisions(tmp_path):
    body = ("1. [A](https://x/1) — Acme\n2. [B](https://x/2) — Beta\n3. [C](https://x/3) — Gamma\n"
            '<!-- scout-items {"1": "k1", "2": "k2", "3": "k3"} -->\n')
    first = label_lines(body, "apply 1", issue=5)
    second = label_lines(body, "maybe 2 · skip rest", issue=5, earlier=first)
    assert {k: v["decision"] for k, v in latest(first + second).items()} == {"k1": "apply", "k2": "maybe", "k3": "skip"}


# L3 — a malformed item map is a parse error (the workflow replies), not a crash.
def test_malformed_item_map_is_a_parse_error():
    with pytest.raises(LabelParseError):
        item_map_of('<!-- scout-items {"1": bad} -->')


# L2 — a negated stipend is not a stipend.
@pytest.mark.parametrize("body", ["This internship does not offer a stipend.", "There is no stipend for this role."])
def test_negated_stipend_is_unstated(body):
    assert pay_of(_opp(body))[0] == "unstated"


def test_plain_stipend_still_stipend():
    assert pay_of(_opp("A monthly stipend of $300 is provided."))[0] == "stipend"
