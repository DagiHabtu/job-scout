"""Persistence + lifecycle diff — NEW/UPDATED/ACTIVE, notified_at preservation, JSON round-trip."""

from __future__ import annotations

import json
from datetime import date

from job_scout.models import (
    Eligibility,
    EligibilityCategory as EC,
    EmploymentType,
    Lifecycle,
    Opportunity,
    Relevance,
)
from job_scout.store import connect, mark_notified, upsert_and_reconcile


def _opp(**kw) -> Opportunity:
    base = dict(
        title="Data Engineer Intern",
        company="Globex",
        apply_url="https://x/1",
        canonical_url="https://x/1",
        content_fingerprint="fp1",
    )
    base.update(kw)
    return Opportunity(**base)


def test_new_then_active_then_updated():
    conn = connect(":memory:")

    a = _opp(description="v1")
    counts1 = upsert_and_reconcile(conn, [a], "r1")
    assert a.status == Lifecycle.NEW and counts1["new"] == 1

    b = _opp(description="v1")  # identical content next run → ACTIVE
    counts2 = upsert_and_reconcile(conn, [b], "r2")
    assert b.status == Lifecycle.ACTIVE and counts2["active"] == 1

    c = _opp(description="v2 — now with more detail")  # content changed → UPDATED
    counts3 = upsert_and_reconcile(conn, [c], "r3")
    assert c.status == Lifecycle.UPDATED and counts3["updated"] == 1


def test_ats_identity_key_takes_precedence_over_fingerprint():
    conn = connect(":memory:")
    a = _opp(ats_provider="greenhouse", ats_job_id="42", content_fingerprint="fpA", description="v1")
    upsert_and_reconcile(conn, [a], "r1")
    # Same ATS id but a DIFFERENT fingerprint (e.g. retitled) is still the SAME record.
    b = _opp(ats_provider="greenhouse", ats_job_id="42", content_fingerprint="fpB", description="v1")
    upsert_and_reconcile(conn, [b], "r2")
    assert b.status == Lifecycle.ACTIVE


def test_notified_at_is_preserved_across_runs():
    conn = connect(":memory:")
    a = _opp()
    upsert_and_reconcile(conn, [a], "r1")
    mark_notified(conn, [a])
    assert a.notified_at is not None

    b = _opp()  # a fresh object for the next run — must inherit notified_at from the store
    upsert_and_reconcile(conn, [b], "r2")
    assert b.notified_at is not None


def test_serialize_round_trip_through_the_raw_column():
    conn = connect(":memory:")
    opp = _opp(
        employment_type=EmploymentType.INTERNSHIP,
        deadline=date(2026, 12, 31),
        eligibility=Eligibility(EC.WORLDWIDE_REMOTE, 0.75, ["worldwide remote"]),
        relevance=Relevance(score=0.8, matched_signals=["tech: python"]),
    )
    upsert_and_reconcile(conn, [opp], "r1")
    row = conn.execute("SELECT raw FROM opportunities WHERE key = ?", ("fp1",)).fetchone()
    data = json.loads(row["raw"])                       # must be valid JSON (enums/dates/nested)
    assert data["title"] == opp.title
    assert data["employment_type"] == "internship"      # enum → value
    assert data["deadline"] == "2026-12-31"             # date → str
    assert data["eligibility"]["category"] == "worldwide_remote"
    assert data["relevance"]["score"] == 0.8
